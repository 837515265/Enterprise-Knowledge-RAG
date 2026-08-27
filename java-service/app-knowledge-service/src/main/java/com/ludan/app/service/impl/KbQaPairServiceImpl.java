package com.ludan.app.service.impl;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.central.common.service.impl.SuperServiceImpl;
import com.ludan.app.entity.KbKnowledgeBase;
import com.ludan.app.entity.KbQaPair;
import com.ludan.app.mapper.KbQaPairMapper;
import com.ludan.app.service.KbKnowledgeBaseService;
import com.ludan.app.service.KbQaPairService;
import com.ludan.app.service.RetrievalEngineClient;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.apache.commons.collections4.MapUtils;
import org.apache.commons.csv.CSVFormat;
import org.apache.commons.csv.CSVParser;
import org.apache.commons.csv.CSVRecord;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.PushbackInputStream;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * 问答对 Service 实现
 *
 * @author ludan
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class KbQaPairServiceImpl
        extends SuperServiceImpl<KbQaPairMapper, KbQaPair>
        implements KbQaPairService {

    private static final int CSV_IMPORT_MAX_ROWS = 500;

    private final KbKnowledgeBaseService knowledgeBaseService;
    private final RetrievalEngineClient retrievalEngineClient;

    @Override
    public Page<KbQaPair> findList(Map<String, Object> params) {
        Page<KbQaPair> page = new Page<>(
                MapUtils.getInteger(params, "pageNo", 1),
                MapUtils.getInteger(params, "pageSize", 10)
        );
        return baseMapper.findList(page, params);
    }

    @Override
    public KbQaPair createQa(Long kbId, String question, String answer) {
        KbQaPair qa = new KbQaPair();
        qa.setKbId(kbId);
        qa.setQuestion(question);
        qa.setAnswer(answer);
        KbKnowledgeBase kb = knowledgeBaseService.getById(kbId);
        qa.setAuditStatus(resolveInitialAuditStatus(kb));
        qa.setIndexSyncStatus("none");
        this.save(qa);
        if (!isQaAuditEnabled(kb)) {
            triggerQaIndexSync(kbId, Collections.singletonList(qa.getId()));
        }
        return qa;
    }

    @Override
    public void updateQa(Long qaId, String question, String answer) {
        KbQaPair qa = this.getById(qaId);
        if (qa == null) {
            throw new RuntimeException("问答对不存在");
        }
        if (question != null) {
            qa.setQuestion(question);
        }
        if (answer != null) {
            qa.setAnswer(answer);
        }
        KbKnowledgeBase kb = knowledgeBaseService.getById(qa.getKbId());
        qa.setAuditStatus(resolveInitialAuditStatus(kb));
        this.updateById(qa);
        if (!isQaAuditEnabled(kb)) {
            triggerQaIndexSync(qa.getKbId(), Collections.singletonList(qaId));
        }
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public int importCsv(Long kbId, MultipartFile file) {
        if (file == null) {
            throw new RuntimeException("导入文件不能为空");
        }
        KbKnowledgeBase kb = knowledgeBaseService.getById(kbId);
        if (kb == null) {
            throw new RuntimeException("知识库不存在: kbId=" + kbId);
        }
        String auditStatus = resolveInitialAuditStatus(kb);
        Map<String, KbQaPair> qaByQuestion = new LinkedHashMap<>();
        List<String> duplicateQuestions = new ArrayList<>();
        int invalidCount = 0;

        try (CSVParser parser = CSVFormat.DEFAULT.parse(createCsvReader(file.getInputStream()))) {
            Iterator<CSVRecord> it = parser.iterator();
            if (!it.hasNext()) {
                return 0;
            }
            CSVRecord header = it.next();
            if (header.size() < 2 || !"question".equalsIgnoreCase(header.get(0).trim())) {
                throw new RuntimeException("CSV格式错误: 首行表头必须为 question,answer");
            }
            while (it.hasNext()) {
                CSVRecord record = it.next();
                if (record.size() < 2) {
                    invalidCount++;
                    continue;
                }
                String question = record.get(0).trim();
                if (question.isEmpty()) {
                    invalidCount++;
                    continue;
                }
                String answer = record.stream().skip(1).collect(Collectors.joining(",")).trim();
                KbQaPair existing = qaByQuestion.get(question);
                if (existing != null) {
                    duplicateQuestions.add(question);
                    if (existing.getAnswer().isEmpty() && !answer.isEmpty()) {
                        existing.setAnswer(answer);
                    }
                    continue;
                }
                KbQaPair qa = new KbQaPair();
                qa.setKbId(kbId);
                qa.setQuestion(question);
                qa.setAnswer(answer);
                qa.setAuditStatus(auditStatus);
                qa.setIndexSyncStatus("none");
                qaByQuestion.put(question, qa);
            }
        } catch (RuntimeException e) {
            throw e;
        } catch (Exception e) {
            throw new RuntimeException("CSV解析失败: " + e.getMessage(), e);
        }

        List<KbQaPair> batchList = new ArrayList<>(qaByQuestion.values());
        if (invalidCount > 0) {
            log.warn("CSV导入跳过无效记录 {} 条, kbId={}", invalidCount, kbId);
        }
        if (!duplicateQuestions.isEmpty()) {
            List<String> samples = duplicateQuestions.stream().distinct().limit(10)
                    .map(q -> q.replace("\r", " ").replace("\n", " "))
                    .map(q -> q.length() > 50 ? q.substring(0, 50) + "..." : q)
                    .collect(Collectors.toList());
            log.warn("CSV导入检测到文件内重复 question {} 条(已去重), 重复项示例: {}, kbId={}",
                    duplicateQuestions.size(), samples, kbId);
        }
        if (batchList.isEmpty()) {
            return 0;
        }
        if (batchList.size() > CSV_IMPORT_MAX_ROWS) {
            throw new RuntimeException("单次导入最多 " + CSV_IMPORT_MAX_ROWS + " 条，当前 " + batchList.size() + " 条");
        }

        for (KbQaPair qa : batchList) {
            this.save(qa);
        }
        if (!isQaAuditEnabled(kb)) {
            List<Long> qaIds = batchList.stream().map(KbQaPair::getId).collect(Collectors.toList());
            triggerQaIndexSync(kbId, qaIds);
        }
        log.info("CSV导入完成: kbId={}, count={}", kbId, batchList.size());
        return batchList.size();
    }

    private Reader createCsvReader(InputStream in) throws IOException {
        PushbackInputStream pbis = new PushbackInputStream(in, 3);
        byte[] bom = new byte[3];
        int n = pbis.read(bom, 0, 3);
        boolean hasBom = n == 3 && bom[0] == (byte) 0xEF && bom[1] == (byte) 0xBB && bom[2] == (byte) 0xBF;
        if (!hasBom && n > 0) {
            pbis.unread(bom, 0, n);
        }
        return new InputStreamReader(pbis, StandardCharsets.UTF_8);
    }

    @Override
    public int deleteQas(Long kbId, List<Long> qaIds) {
        if (qaIds == null || qaIds.isEmpty()) {
            return 0;
        }
        List<Long> validIds = new ArrayList<>();
        for (Long qaId : qaIds) {
            KbQaPair qa = this.getById(qaId);
            if (qa == null || !kbId.equals(qa.getKbId())) {
                log.warn("删除QA跳过：qaId={} 不属于 kbId={}", qaId, kbId);
                continue;
            }
            validIds.add(qaId);
        }
        if (!validIds.isEmpty()) {
            this.removeByIds(validIds);
            try {
                retrievalEngineClient.deleteQaIndex(kbId, validIds);
            } catch (Exception e) {
                log.warn("QA删除后索引同步失败 kbId={} msg={}", kbId, e.getMessage());
            }
        }
        return validIds.size();
    }

    private String resolveInitialAuditStatus(KbKnowledgeBase kb) {
        return kb != null && Integer.valueOf(1).equals(kb.getQaAuditEnabled()) ? "pending" : "approved";
    }

    private boolean isQaAuditEnabled(KbKnowledgeBase kb) {
        return kb != null && Integer.valueOf(1).equals(kb.getQaAuditEnabled());
    }

    private void triggerQaIndexSync(Long kbId, List<Long> qaIds) {
        if (qaIds == null || qaIds.isEmpty()) {
            return;
        }
        if (TransactionSynchronizationManager.isSynchronizationActive()) {
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    try {
                        retrievalEngineClient.indexQas(kbId, qaIds);
                    } catch (Exception e) {
                        log.warn("QA索引同步失败(afterCommit) kbId={} qaIds={} msg={}", kbId, qaIds, e.getMessage());
                    }
                }
            });
        } else {
            try {
                retrievalEngineClient.indexQas(kbId, qaIds);
            } catch (Exception e) {
                log.warn("QA索引同步失败 kbId={} qaIds={} msg={}", kbId, qaIds, e.getMessage());
            }
        }
    }
}
