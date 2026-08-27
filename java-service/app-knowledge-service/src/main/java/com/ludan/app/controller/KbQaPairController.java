package com.ludan.app.controller;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.central.common.model.PageResult;
import com.central.common.model.Result;
import com.ludan.app.entity.KbQaPair;
import com.ludan.app.service.KbQaPairService;
import com.ludan.app.service.RetrievalEngineClient;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.util.HashMap;
import java.util.Map;

/**
 * 问答对管理 Controller
 *
 * @author ludan
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/kb/knowledge-bases/{kbId}/qa-pairs")
@Api(tags = "问答对管理")
@RequiredArgsConstructor
public class KbQaPairController {

    private final KbQaPairService qaPairService;
    private final RetrievalEngineClient retrievalEngineClient;

    @ApiOperation("问答对列表")
    @GetMapping
    public PageResult<KbQaPair> list(@PathVariable Long kbId, @RequestParam Map<String, Object> params) {
        params.put("kbId", kbId);
        Page<KbQaPair> page = qaPairService.findList(params);
        return PageResult.<KbQaPair>builder()
                .data(page.getRecords())
                .code(0)
                .count(page.getTotal())
                .build();
    }

    @ApiOperation("创建问答对")
    @PostMapping
    public Result<KbQaPair> create(@PathVariable Long kbId, @RequestBody Map<String, String> body) {
        String question = body.get("question");
        String answer = body.get("answer");
        KbQaPair qa = qaPairService.createQa(kbId, question, answer);
        return Result.succeed(qa, "创建成功");
    }

    @ApiOperation("更新问答对")
    @PutMapping("/{qaId}")
    public Result<Void> update(@PathVariable Long kbId, @PathVariable Long qaId,
                               @RequestBody Map<String, String> body) {
        qaPairService.updateQa(qaId, body.get("question"), body.get("answer"));
        return Result.succeed(null, "更新成功");
    }

    @ApiOperation("删除问答对")
    @DeleteMapping("/{qaId}")
    public Result<Void> delete(@PathVariable Long kbId, @PathVariable Long qaId) {
        qaPairService.deleteQas(kbId, java.util.Collections.singletonList(qaId));
        return Result.succeed(null, "删除成功");
    }

    @ApiOperation("CSV批量导入")
    @PostMapping("/import")
    public Result<Integer> importCsv(@PathVariable Long kbId, @RequestParam("file") MultipartFile file) {
        int count = qaPairService.importCsv(kbId, file);
        return Result.succeed(count, "导入成功，共 " + count + " 条");
    }

    @ApiOperation("下载导入模板")
    @GetMapping("/template")
    public void downloadTemplate(@PathVariable Long kbId,
                                 javax.servlet.http.HttpServletResponse response) throws Exception {
        response.setContentType("text/csv;charset=UTF-8");
        response.setHeader("Content-Disposition", "attachment;filename=qa-template.csv");
        response.getWriter().write("question,answer\n");
        response.getWriter().write("示例问题,示例答案\n");
        response.getWriter().flush();
    }

    @ApiOperation("QA 全部索引")
    @PostMapping("/reindex")
    public Result<Map<String, Object>> reindexQas(@PathVariable Long kbId) {
        try {
            String indexGeneration = retrievalEngineClient.rebuildQaIndex(kbId);
            Map<String, Object> data = new HashMap<>();
            data.put("indexGeneration", indexGeneration);
            return Result.succeed(data, "已触发 QA 全部索引");
        } catch (RuntimeException e) {
            log.warn("QA 全部索引失败: kbId={}, msg={}", kbId, e.getMessage());
            return Result.failed(e.getMessage());
        }
    }
}
