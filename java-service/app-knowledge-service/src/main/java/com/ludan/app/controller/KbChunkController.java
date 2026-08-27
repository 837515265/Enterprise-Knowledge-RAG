package com.ludan.app.controller;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.central.common.model.PageResult;
import com.central.common.model.Result;
import com.ludan.app.dto.resp.ChunkStatsRespDTO;
import com.ludan.app.entity.KbChunk;
import com.ludan.app.service.KbChunkService;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * Chunk 管理 Controller
 *
 * @author ludan
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/kb/knowledge-bases/{kbId}")
@Api(tags = "Chunk管理")
@RequiredArgsConstructor
public class KbChunkController {

    private final KbChunkService chunkService;

    @ApiOperation("查询文件下的Chunk列表")
    @GetMapping("/files/{fileId}/chunks")
    public PageResult<KbChunk> chunkList(@PathVariable Long kbId, @PathVariable Long fileId,
                                         @RequestParam Map<String, Object> params) {
        params.put("kbId", kbId);
        params.put("fileNodeId", fileId);
        Page<KbChunk> page = chunkService.findByFileNode(params);
        return PageResult.<KbChunk>builder()
                .data(page.getRecords())
                .code(0)
                .count(page.getTotal())
                .build();
    }

    @ApiOperation("Chunk统计")
    @GetMapping("/files/{fileId}/chunk-stats")
    public Result<ChunkStatsRespDTO> chunkStats(@PathVariable Long kbId, @PathVariable Long fileId) {
        ChunkStatsRespDTO stats = chunkService.getChunkStats(fileId);
        return Result.succeed(stats, "查询成功");
    }

    @ApiOperation("编辑Chunk（创建新revision）")
    @PutMapping("/chunks/{chunkId}")
    public Result<Void> editChunk(@PathVariable Long kbId, @PathVariable Long chunkId,
                                  @RequestBody Map<String, String> body) {
        String content = body.get("content");
        String editReason = body.get("editReason");
        chunkService.editChunk(chunkId, content, editReason);
        return Result.succeed(null, "编辑成功");
    }

    @ApiOperation("启用/禁用Chunk")
    @PutMapping("/chunks/{chunkId}/enabled")
    public Result<Void> toggleEnabled(@PathVariable Long kbId, @PathVariable Long chunkId,
                                      @RequestBody Map<String, Object> body) {
        boolean enabled = Boolean.TRUE.equals(body.get("enabled"));
        chunkService.toggleEnabled(chunkId, enabled);
        return Result.succeed(null, "操作成功");
    }

    @ApiOperation("删除Chunk")
    @DeleteMapping("/chunks/{chunkId}")
    public Result<Void> deleteChunk(@PathVariable Long kbId, @PathVariable Long chunkId) {
        chunkService.deleteChunk(kbId, chunkId);
        return Result.succeed(null, "删除成功");
    }
}
