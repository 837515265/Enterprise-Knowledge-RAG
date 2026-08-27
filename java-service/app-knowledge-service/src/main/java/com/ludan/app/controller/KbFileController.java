package com.ludan.app.controller;

import com.central.common.model.Result;
import com.ludan.app.dto.req.KbBatchCreateFileReqDTO;
import com.ludan.app.dto.resp.KbBatchCreateFileResultDTO;
import com.ludan.app.entity.KbFileNode;
import com.ludan.app.service.KbDocumentAnalysisService;
import com.ludan.app.service.KbFileNodeService;
import com.ludan.app.service.RetrievalEngineClient;
import com.ludan.app.service.impl.KbParseTaskStatusSyncService;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 知识库文件管理 Controller
 *
 * @author ludan
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/kb/knowledge-bases/{kbId}/files")
@Api(tags = "知识库文件管理")
@RequiredArgsConstructor
public class KbFileController {

    private final KbFileNodeService fileNodeService;
    private final KbDocumentAnalysisService documentAnalysisService;
    private final RetrievalEngineClient retrievalEngineClient;
    private final KbParseTaskStatusSyncService parseTaskStatusSyncService;

    @ApiOperation(value = "获取文件树")
    @GetMapping
    public Result<List<KbFileNode>> fileTree(@PathVariable Long kbId) {
        List<KbFileNode> tree = fileNodeService.getFileTree(kbId);
        return Result.succeed(tree, "查询成功");
    }

    @ApiOperation(value = "新增知识库文件")
    @PostMapping
    public Result<List<KbBatchCreateFileResultDTO>> create(@PathVariable Long kbId,
                                                           @RequestBody KbBatchCreateFileReqDTO reqDTO) {
        try {
            List<KbBatchCreateFileResultDTO> results = fileNodeService.batchCreateFileNodes(kbId, reqDTO.getParentId(),
                    reqDTO.getParseStrategyConfigId(), reqDTO.getFiles());
            return Result.succeed(results, "上传完成");
        } catch (RuntimeException e) {
            log.warn("新增知识库文件失败: kbId={}, message={}", kbId, e.getMessage());
            return Result.failed(e.getMessage());
        }
    }

    @ApiOperation(value = "创建文件夹")
    @PostMapping("/folder")
    public Result<KbFileNode> createFolder(@PathVariable Long kbId, @RequestBody Map<String, Object> body) {
        Long parentId = body.get("parentId") != null ? Long.valueOf(body.get("parentId").toString()) : null;
        String folderName = (String) body.get("name");
        KbFileNode node = fileNodeService.createFolderNode(kbId, parentId, folderName);
        return Result.succeed(node, "创建成功");
    }

    @ApiOperation(value = "重命名文件/文件夹")
    @PutMapping("/{fileId}")
    public Result<Void> renameNode(@PathVariable Long kbId, @PathVariable Long fileId,
                                   @RequestBody Map<String, Object> body) {
        String nodeName = (String) body.get("name");
        fileNodeService.renameNode(kbId, fileId, nodeName);
        return Result.succeed(null, "重命名成功");
    }

    @ApiOperation(value = "移动文件/文件夹")
    @PutMapping("/{fileId}/move")
    public Result<Void> move(@PathVariable Long kbId, @PathVariable Long fileId, @RequestBody Map<String, Object> body) {
        Long parentId = body.get("parentId") != null ? Long.valueOf(body.get("parentId").toString()) : null;
        fileNodeService.moveNode(kbId, fileId, parentId);
        return Result.succeed(null, "移动成功");
    }

    @ApiOperation(value = "删除文件/文件夹")
    @DeleteMapping("/{fileId}")
    public Result<Void> delete(@PathVariable Long kbId, @PathVariable Long fileId) {
        fileNodeService.deleteNode(kbId, fileId);
        return Result.succeed(null, "删除成功");
    }

    @ApiOperation(value = "重新解析")
    @PostMapping("/{fileId}/reparse")
    public Result<Void> reparse(@PathVariable Long kbId, @PathVariable Long fileId) {
        fileNodeService.triggerReparse(kbId, fileId);
        return Result.succeed(null, "已触发重解析");
    }

    @ApiOperation(value = "获取文档知识图谱")
    @GetMapping("/{fileId}/graph")
    public Result<Map<String, Object>> graph(@PathVariable Long kbId,
                                              @PathVariable Long fileId,
                                              @RequestParam(defaultValue = "false") boolean includeChunks) {
        KbFileNode fileNode = fileNodeService.getById(fileId);
        if (fileNode == null || !kbId.equals(fileNode.getKbId()) || !"file".equals(fileNode.getNodeType())) {
            return Result.failed("文件不存在");
        }
        try {
            return Result.succeed(retrievalEngineClient.getFileGraph(kbId, fileId, includeChunks), "查询成功");
        } catch (RuntimeException e) {
            log.warn("读取文件图谱失败: kbId={}, fileId={}, message={}", kbId, fileId, e.getMessage());
            return Result.failed(e.getMessage());
        }
    }

    @ApiOperation(value = "获取文档结构化解析结果")
    @GetMapping("/{fileId}/analysis")
    public Result<Map<String, Object>> analysis(@PathVariable Long kbId, @PathVariable Long fileId) {
        try {
            return Result.succeed(documentAnalysisService.getAnalysis(kbId, fileId), "查询成功");
        } catch (RuntimeException e) {
            log.warn("读取文档结构化解析结果失败: kbId={}, fileId={}, message={}", kbId, fileId, e.getMessage());
            return Result.failed(e.getMessage());
        }
    }

    @ApiOperation(value = "重新解析全部")
    @PostMapping("/reparse-all")
    public Result<Map<String, Object>> reparseAll(@PathVariable Long kbId) {
        try {
            int count = fileNodeService.triggerReparseAll(kbId);
            Map<String, Object> data = new java.util.HashMap<>();
            data.put("triggeredCount", count);
            return Result.succeed(data, "已触发 " + count + " 个文件的重新解析");
        } catch (RuntimeException e) {
            log.warn("重新解析全部失败: kbId={}, message={}", kbId, e.getMessage());
            return Result.failed(e.getMessage());
        }
    }

    @ApiOperation(value = "按目录重新解析全部")
    @PostMapping("/{folderId}/reparse-all")
    public Result<Map<String, Object>> reparseAllByFolder(@PathVariable Long kbId, @PathVariable Long folderId) {
        try {
            int count = fileNodeService.triggerReparseAll(kbId, folderId);
            Map<String, Object> data = new java.util.HashMap<>();
            data.put("triggeredCount", count);
            return Result.succeed(data, "已触发 " + count + " 个文件的重新解析");
        } catch (RuntimeException e) {
            log.warn("按目录重新解析失败: kbId={}, folderId={}, message={}", kbId, folderId, e.getMessage());
            return Result.failed(e.getMessage());
        }
    }

    @ApiOperation(value = "重新索引")
    @PostMapping("/reindex")
    public Result<Map<String, Object>> reindex(@PathVariable Long kbId) {
        try {
            String taskId = retrievalEngineClient.rebuildKbIndex(kbId);
            Map<String, Object> data = new java.util.HashMap<>();
            data.put("taskId", taskId);
            return Result.succeed(data, "已触发知识库重新索引");
        } catch (RuntimeException e) {
            log.warn("重新索引失败: kbId={}, message={}", kbId, e.getMessage());
            return Result.failed(e.getMessage());
        }
    }

    @ApiOperation(value = "重新索引（单文件）")
    @PostMapping("/{fileId}/reindex")
    public Result<Void> reindexFile(@PathVariable Long kbId, @PathVariable Long fileId) {
        try {
            parseTaskStatusSyncService.rebuildFileIndex(kbId, fileId);
            return Result.succeed(null, "已触发重新索引");
        } catch (RuntimeException e) {
            log.warn("重新索引失败: kbId={}, fileId={}, message={}", kbId, fileId, e.getMessage());
            return Result.failed(e.getMessage());
        }
    }
}
