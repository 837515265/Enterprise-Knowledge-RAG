package com.ludan.app.service.model;

import lombok.Getter;
import lombok.Setter;

/**
 * 解析引擎任务状态快照
 *
 * @author ludan
 */
@Getter
@Setter
public class ParseTaskStatusSnapshot {

    /** 平台侧任务ID */
    private Long taskId;

    /** 引擎内部任务ID */
    private String engineTaskId;

    /** 当前阶段 */
    private String stage;

    /** 引擎侧原始状态 */
    private String status;

    /** 已产出 chunk 数量 */
    private Integer chunkCount;

    /** 失败原因 */
    private String errorMsg;
}
