package com.ludan.app.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.ludan.app.dto.resp.KbSearchFileItemDTO;
import com.ludan.app.entity.KbFileNode;
import com.ludan.app.entity.KbKnowledgeBase;
import com.ludan.app.mapper.KbFileNodeMapper;
import com.ludan.app.mapper.KbKnowledgeBaseMapper;
import com.ludan.app.config.RetrievalEngineProperties;
import com.ludan.app.service.KbPermissionService;
import com.ludan.app.service.KbSearchService;
import com.ludan.app.service.RetrievalEngineClient;
import com.ludan.app.service.model.RetrievalEngineHit;
import com.ludan.app.support.KbRagProfileResolver;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

import javax.servlet.http.HttpServletRequest;
import java.text.DecimalFormat;
import java.text.SimpleDateFormat;
import java.util.*;
import java.util.stream.Collectors;

/**
 * 搜文件：调用外部检索微服务并按文件聚合展示。
 *
 * @author ludan
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class KbSearchServiceImpl implements KbSearchService {

    private final KbKnowledgeBaseMapper knowledgeBaseMapper;
    private final KbPermissionService permissionService;
    private final KbFileNodeMapper fileNodeMapper;
    private final RetrievalEngineClient retrievalEngineClient;
    private final RetrievalEngineProperties retrievalEngineProperties;
    private final KbRagProfileResolver ragProfileResolver;

    @Override
    public List<KbSearchFileItemDTO> searchFiles(String keyword, Long kbId, String fileType, Boolean titleOnly) {
        String userId = resolveCurrentUserId();
        List<KbKnowledgeBase> scoped = listActiveKbsForSearch(kbId);
        List<KbKnowledgeBase> allowed = scoped.stream()
                .filter(kb -> permissionService.canUseKb(kb, userId))
                .collect(Collectors.toList());
        if (allowed.isEmpty()) {
            log.debug("搜文件: 无可用知识库或无权访问, kbId={}", kbId);
            return new ArrayList<>();
        }

        boolean onlyTitle = Boolean.TRUE.equals(titleOnly);
        int topK = retrievalEngineProperties.getDefaultTopK();
        // titleOnly 时通过 options.routes 限制只走 bm25
        Map<String, Object> searchOverrides = null;
        if (onlyTitle) {
            Map<String, Object> routes = new HashMap<>();
            routes.put("qa_enabled", false);
            routes.put("graph_enabled", false);
            routes.put("bm25_enabled", true);
            routes.put("vector_enabled", false);
            routes.put("structured_enabled", false);
            routes.put("section_summary_enabled", false);
            searchOverrides = new HashMap<>();
            searchOverrides.put("routes", routes);
        }

        List<RetrievalEngineHit> hits;
        if (allowed.size() == 1) {
            // 单库路径
            hits = retrievalEngineClient.retrieveForKnowledgeBases(
                    Collections.singletonList(allowed.get(0).getId()), keyword, topK,
                    ragProfileResolver.buildRetrieveOptions(allowed.get(0), searchOverrides));
        } else {
            // 多库路径：单次 HTTP
            List<Long> kbIds = allowed.stream().map(KbKnowledgeBase::getId).collect(Collectors.toList());
            Map<String, Object> options = ragProfileResolver.buildRetrieveOptions(allowed.get(0), searchOverrides);
            int totalTopK = Math.min(topK * kbIds.size(), 200);
            hits = retrievalEngineClient.retrieveForKnowledgeBases(
                    kbIds, keyword, totalTopK, options);
        }

        Set<Long> allowedKbIds = allowed.stream().map(KbKnowledgeBase::getId).collect(Collectors.toSet());

        String kwLower = keyword == null ? "" : keyword.trim().toLowerCase(Locale.ROOT);
        Map<Long, Agg> aggByFile = new HashMap<>();
        for (RetrievalEngineHit hit : hits) {
            Map<String, Object> meta = hit.getMetadata();
            if (meta == null) {
                continue;
            }
            Long fileNodeId = metaLong(meta, "file_node_id");
            if (fileNodeId == null) {
                continue;
            }
            KbFileNode probeNode = fileNodeMapper.selectById(fileNodeId);
            if (probeNode == null || !"file".equals(probeNode.getNodeType())) {
                continue;
            }
            Long resolvedKbId = probeNode.getKbId();
            KbKnowledgeBase kb = knowledgeBaseMapper.selectById(resolvedKbId);
            if (kb == null || !Objects.equals(kb.getStatus(), "active")) {
                continue;
            }
            if (!permissionService.canUseKb(kb, userId)) {
                continue;
            }
            if (!allowedKbIds.contains(kb.getId())) {
                continue;
            }

            String fileName = metaString(meta, "file_name");
            if (fileName == null || fileName.trim().isEmpty()) {
                fileName = firstNonBlank(probeNode.getOriginalName(), probeNode.getName());
            }
            String titleMeta = metaString(meta, "title");

            if (onlyTitle) {
                boolean hitTitle = containsIgnoreCase(titleMeta, kwLower)
                        || containsIgnoreCase(fileName, kwLower);
                if (!hitTitle) {
                    continue;
                }
            }

            Agg agg = aggByFile.computeIfAbsent(fileNodeId, id -> new Agg());
            double sc = hit.getScore() != null ? hit.getScore() : 0d;
            if (sc > agg.bestScore) {
                agg.bestScore = sc;
                agg.bestSnippet = hit.getSnippet();
            }
            agg.kbId = resolvedKbId;
        }

        if (aggByFile.isEmpty()) {
            return new ArrayList<>();
        }

        Set<Long> ids = aggByFile.keySet();
        List<KbFileNode> nodes = fileNodeMapper.selectBatchIds(ids);
        Map<Long, KbFileNode> nodeById = nodes.stream()
                .filter(n -> "file".equals(n.getNodeType()))
                .collect(Collectors.toMap(KbFileNode::getId, n -> n, (a, b) -> a));

        List<KbSearchFileItemDTO> out = new ArrayList<>();
        SimpleDateFormat sdf = new SimpleDateFormat("yyyy-MM-dd HH:mm");
        for (Map.Entry<Long, Agg> e : aggByFile.entrySet()) {
            Long fid = e.getKey();
            Agg agg = e.getValue();
            KbFileNode node = nodeById.get(fid);
            KbKnowledgeBase kb = knowledgeBaseMapper.selectById(agg.kbId);
            if (kb == null) {
                continue;
            }

            KbSearchFileItemDTO dto = new KbSearchFileItemDTO();
            dto.setId(fid);
            dto.setKbId(kb.getId());
            dto.setKbName(kb.getName());
            dto.setScore(agg.bestScore);
            dto.setSnippet(agg.bestSnippet);
            dto.setDescription(agg.bestSnippet);

            if (node != null) {
                dto.setFileId(node.getFileId());
                String rawName = firstNonBlank(node.getOriginalName(), node.getName());
                String displayName = rawName.isEmpty() ? "" : KbFileNodeServiceImpl.normalizeFileName(rawName);
                dto.setTitle(displayName);
                dto.setName(displayName);
                dto.setFileType(summarizeFileType(node));
                dto.setSize(formatSize(node.getFileSize()));
                if (node.getUpdateTime() != null) {
                    dto.setUpdateTime(sdf.format(node.getUpdateTime()));
                }
            } else {
                dto.setTitle("文件 " + fid);
                dto.setName(dto.getTitle());
                dto.setFileType("");
                dto.setSize("");
            }

            if (!passFileTypeFilter(dto, fileType)) {
                continue;
            }
            out.add(dto);
        }

        out.sort(Comparator.comparing(KbSearchFileItemDTO::getScore, Comparator.nullsLast(Comparator.reverseOrder())));
        return out;
    }

    private List<KbKnowledgeBase> listActiveKbsForSearch(Long kbId) {
        LambdaQueryWrapper<KbKnowledgeBase> q = new LambdaQueryWrapper<KbKnowledgeBase>()
                .eq(KbKnowledgeBase::getStatus, "active");
        if (kbId != null) {
            q.eq(KbKnowledgeBase::getId, kbId);
        }
        return knowledgeBaseMapper.selectList(q);
    }

    private String resolveCurrentUserId() {
        ServletRequestAttributes attributes = (ServletRequestAttributes) RequestContextHolder.getRequestAttributes();
        if (attributes == null) {
            return null;
        }
        HttpServletRequest request = attributes.getRequest();
        String userId = request.getHeader("x-userid-header");
        Enumeration<String> enumeration =  request.getHeaderNames();
        while (enumeration.hasMoreElements()) {
            String name = enumeration.nextElement();
            log.info("header: {} = {}", name, request.getHeader(name));
        }
        return userId == null || userId.trim().isEmpty() ? null : userId.trim();
    }

    private static Long metaLong(Map<String, Object> meta, String key) {
        Object v = meta.get(key);
        if (v == null) {
            return null;
        }
        if (v instanceof Number) {
            return ((Number) v).longValue();
        }
        try {
            return Long.parseLong(v.toString().trim());
        } catch (Exception e) {
            return null;
        }
    }

    private static String metaString(Map<String, Object> meta, String key) {
        Object v = meta.get(key);
        return v == null ? null : v.toString();
    }

    private static boolean containsIgnoreCase(String text, String kwLower) {
        if (text == null || kwLower.isEmpty()) {
            return false;
        }
        return text.toLowerCase(Locale.ROOT).contains(kwLower);
    }

    private static boolean passFileTypeFilter(KbSearchFileItemDTO dto, String fileType) {
        if (fileType == null || fileType.trim().isEmpty()) {
            return true;
        }
        String t = fileType.trim().toLowerCase(Locale.ROOT);
        String pool = ((dto.getFileType() != null ? dto.getFileType() : "") + " "
                + (dto.getName() != null ? dto.getName() : "")).toLowerCase(Locale.ROOT);
        if ("pdf".equals(t)) {
            return pool.contains("pdf");
        }
        if ("word".equals(t)) {
            return pool.contains("word") || pool.contains("doc");
        }
        if ("excel".equals(t)) {
            return pool.contains("excel") || pool.contains("xls");
        }
        return true;
    }

    private static String firstNonBlank(String a, String b) {
        if (a != null && !a.trim().isEmpty()) {
            return a.trim();
        }
        if (b != null && !b.trim().isEmpty()) {
            return b.trim();
        }
        return "";
    }

    private static String summarizeFileType(KbFileNode node) {
        if (node.getFileExt() != null && !node.getFileExt().trim().isEmpty()) {
            return node.getFileExt().trim().toLowerCase(Locale.ROOT);
        }
        String name = node.getOriginalName() != null ? node.getOriginalName() : node.getName();
        if (name == null || !name.contains(".")) {
            return "";
        }
        return name.substring(name.lastIndexOf('.') + 1).toLowerCase(Locale.ROOT);
    }

    private static String formatSize(Long bytes) {
        if (bytes == null || bytes <= 0) {
            return "";
        }
        if (bytes < 1024) {
            return bytes + " B";
        }
        double kb = bytes / 1024.0;
        if (kb < 1024) {
            return new DecimalFormat("#.#").format(kb) + " KB";
        }
        double mb = kb / 1024.0;
        if (mb < 1024) {
            return new DecimalFormat("#.#").format(mb) + " MB";
        }
        double gb = mb / 1024.0;
        return new DecimalFormat("#.##").format(gb) + " GB";
    }

    private static class Agg {
        double bestScore = -1d;
        String bestSnippet;
        Long kbId;
    }
}
