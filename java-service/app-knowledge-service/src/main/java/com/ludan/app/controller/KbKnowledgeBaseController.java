package com.ludan.app.controller;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.central.common.model.PageResult;
import com.central.common.model.Result;
import com.ludan.app.dto.req.KbCreateReqDTO;
import com.ludan.app.dto.req.KbUpdateReqDTO;
import com.ludan.app.dto.resp.KbListRespDTO;
import com.ludan.app.dto.resp.KbSimpleItemDTO;
import com.ludan.app.entity.KbKnowledgeBase;
import com.ludan.app.service.KbKnowledgeBaseService;
import com.ludan.app.service.RetrievalEngineClient;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiImplicitParam;
import io.swagger.annotations.ApiImplicitParams;
import io.swagger.annotations.ApiOperation;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 知识库管理 Controller
 *
 * @author ludan
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/kb/knowledge-bases")
@Api(tags = "知识库管理")
@RequiredArgsConstructor
public class KbKnowledgeBaseController {

    private final KbKnowledgeBaseService knowledgeBaseService;
    private final RetrievalEngineClient retrievalEngineClient;

    @ApiOperation(value = "分页查询知识库列表")
    @ApiImplicitParams({
            @ApiImplicitParam(name = "pageNo", value = "页码", dataType = "Integer"),
            @ApiImplicitParam(name = "pageSize", value = "每页条数", dataType = "Integer"),
            @ApiImplicitParam(name = "keyword", value = "名称关键词", dataType = "String"),
            @ApiImplicitParam(name = "visibility", value = "公开性 public/private", dataType = "String"),
            @ApiImplicitParam(name = "type", value = "知识库类型", dataType = "String"),
            @ApiImplicitParam(name = "tagId", value = "标签ID筛选", dataType = "Long")
    })
    @GetMapping
    public PageResult<KbListRespDTO> list(@RequestParam Map<String, Object> params) {
        Page<KbListRespDTO> page = knowledgeBaseService.findList(params);
        return PageResult.<KbListRespDTO>builder()
                .data(page.getRecords())
                .code(0)
                .count(page.getTotal())
                .build();
    }

    @ApiOperation(value = "按用户查询可访问知识库（id+name）")
    @ApiImplicitParam(name = "userId", value = "用户ID，为空则仅返回公开库", dataType = "String")
    @GetMapping("/simpleList")
    public Result<List<KbSimpleItemDTO>> simpleList(
            @RequestParam(required = false) String userId) {
        return Result.succeed(knowledgeBaseService.getSimpleList(userId), "查询成功");
    }

    @ApiOperation(value = "知识库详情")
    @GetMapping("/{kbId}")
    public Result<KbListRespDTO> detail(@PathVariable Long kbId) {
        KbListRespDTO detail = knowledgeBaseService.getKbDetail(kbId);
        if (detail == null) {
            return Result.failed("知识库不存在");
        }
        return Result.succeed(detail, "查询成功");
    }

    @ApiOperation(value = "获取知识库知识图谱")
    @GetMapping("/{kbId}/graph")
    public Result<Map<String, Object>> graph(@PathVariable Long kbId,
                                              @RequestParam(defaultValue = "false") boolean includeChunks) {
        if (knowledgeBaseService.getById(kbId) == null) {
            return Result.failed("知识库不存在");
        }
        try {
            return Result.succeed(retrievalEngineClient.getKnowledgeBaseGraph(kbId, includeChunks), "查询成功");
        } catch (RuntimeException e) {
            log.warn("读取知识库图谱失败: kbId={}, message={}", kbId, e.getMessage());
            return Result.failed(e.getMessage());
        }
    }

    @ApiOperation(value = "知识库图谱质量体检")
    @GetMapping("/{kbId}/graph/audit")
    public Result<Map<String, Object>> graphAudit(
            @PathVariable Long kbId,
            @RequestParam(defaultValue = "20") int hubDegree,
            @RequestParam(defaultValue = "100") int limit) {
        if (knowledgeBaseService.getById(kbId) == null) {
            return Result.failed("知识库不存在");
        }
        try {
            return Result.succeed(
                    retrievalEngineClient.getKnowledgeBaseGraphAudit(kbId, hubDegree, limit),
                    "查询成功"
            );
        } catch (RuntimeException e) {
            log.warn("知识库图谱体检失败: kbId={}, message={}", kbId, e.getMessage());
            return Result.failed(e.getMessage());
        }
    }

    @ApiOperation(value = "重建知识库图谱社区")
    @PostMapping("/{kbId}/graph/communities/rebuild")
    public Result<Map<String, Object>> rebuildGraphCommunities(
            @PathVariable Long kbId,
            @RequestParam(defaultValue = "2") int minSize) {
        if (knowledgeBaseService.getById(kbId) == null) {
            return Result.failed("知识库不存在");
        }
        try {
            return Result.succeed(
                    retrievalEngineClient.rebuildKnowledgeBaseGraphCommunities(kbId, minSize),
                    "重建成功"
            );
        } catch (RuntimeException e) {
            log.warn("知识库图谱社区重建失败: kbId={}, message={}", kbId, e.getMessage());
            return Result.failed(e.getMessage());
        }
    }

    @ApiOperation(value = "创建知识库")
    @PostMapping
    public Result<KbKnowledgeBase> create(@RequestBody KbCreateReqDTO reqDTO) {
        KbKnowledgeBase kb = knowledgeBaseService.createKb(reqDTO);
        return Result.succeed(kb, "创建成功");
    }

    @ApiOperation(value = "更新知识库")
    @PutMapping("/{kbId}")
    public Result<Void> update(@PathVariable Long kbId, @RequestBody KbUpdateReqDTO reqDTO) {
        knowledgeBaseService.updateKb(kbId, reqDTO);
        return Result.succeed(null, "更新成功");
    }

    @ApiOperation(value = "删除知识库")
    @DeleteMapping("/{kbId}")
    public Result<Void> delete(@PathVariable Long kbId) {
        knowledgeBaseService.removeById(kbId);
        return Result.succeed(null, "删除成功");
    }
}
