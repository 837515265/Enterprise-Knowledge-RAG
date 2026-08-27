package com.ludan.app.controller;

import com.central.common.model.Result;
import com.ludan.app.dto.resp.KbSearchFileItemDTO;
import com.ludan.app.service.KbSearchService;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import io.swagger.annotations.ApiParam;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 搜文件：转发至外部检索微服务并聚合为文件列表。
 *
 * @author ludan
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/kb")
@Api(tags = "搜文件")
@RequiredArgsConstructor
public class KbSearchController {

    private final KbSearchService kbSearchService;

    @ApiOperation("搜文件（关键词检索，按文件聚合）")
    @GetMapping("/search-files")
    public Result<List<KbSearchFileItemDTO>> searchFiles(
            @ApiParam(value = "关键词", required = true) @RequestParam("keyword") String keyword,
            @ApiParam("限定知识库 ID") @RequestParam(value = "kbId", required = false) Long kbId,
            @ApiParam("文件类型筛选：pdf/word/excel") @RequestParam(value = "fileType", required = false) String fileType,
            @ApiParam("仅标题匹配") @RequestParam(value = "titleOnly", required = false) Boolean titleOnly) {
        if (!StringUtils.hasText(keyword)) {
            return Result.failed("关键词不能为空");
        }
        List<KbSearchFileItemDTO> list = kbSearchService.searchFiles(keyword.trim(), kbId, fileType, titleOnly);
        return Result.succeed(list, "查询成功");
    }
}
