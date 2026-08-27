package com.ludan.app.controller;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.central.common.model.PageResult;
import com.central.common.model.Result;
import com.ludan.app.dto.req.KbFileAuditSubmitReqDTO;
import com.ludan.app.dto.req.KbQaAuditSubmitReqDTO;
import com.ludan.app.entity.KbAuditHistory;
import com.ludan.app.service.KbAuditService;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * 审核管理 Controller
 *
 * @author ludan
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/kb")
@Api(tags = "审核管理")
@RequiredArgsConstructor
public class KbAuditController {

    private final KbAuditService auditService;

    @ApiOperation("文件级审核提交")
    @PostMapping("/knowledge-bases/{kbId}/files/{fileId}/audit/submit")
    public Result<Void> submitFileAudit(@PathVariable Long kbId, @PathVariable Long fileId,
                                        @RequestBody KbFileAuditSubmitReqDTO reqDTO) {
        auditService.submitFileAudit(kbId, fileId, reqDTO.getStatus(), reqDTO.getReviewComment(),
                reqDTO.getApprovedIds(), reqDTO.getRejectedIds(), reqDTO.getRejectReason(),
                reqDTO.getRejectedReasons());
        return Result.succeed(null, "审核提交成功");
    }

    @ApiOperation("QA审核提交")
    @PostMapping("/knowledge-bases/{kbId}/qa-pairs/{qaId}/audit/submit")
    public Result<Void> submitQaAudit(@PathVariable Long kbId, @PathVariable Long qaId,
                                      @RequestBody KbQaAuditSubmitReqDTO reqDTO) {
        auditService.submitQaAudit(kbId, qaId, reqDTO.getStatus(), reqDTO.getReviewComment());
        return Result.succeed(null, "审核提交成功");
    }

    @ApiOperation("审核历史")
    @GetMapping("/knowledge-bases/{kbId}/audit/history")
    public PageResult<KbAuditHistory> auditHistory(@PathVariable Long kbId,
                                                    @RequestParam Map<String, Object> params) {
        params.put("kbId", kbId);
        Page<KbAuditHistory> page = auditService.getHistory(params);
        return PageResult.<KbAuditHistory>builder()
                .data(page.getRecords())
                .code(0)
                .count(page.getTotal())
                .build();
    }
}
