package com.ludan.app.service;

import com.ludan.app.entity.KbFileTask;
import com.ludan.app.service.model.ParseTaskStatusSnapshot;

/**
 * 解析引擎客户端接口
 * <p>
 * 抽象解析引擎的调用，正式对接时替换实现即可，无需修改业务代码。
 *
 * @author ludan
 */
public interface ParseEngineClient {

    /**
     * 提交解析任务到引擎
     *
     * @param task             平台侧解析任务（已落库）
     * @param modelProfileJson 模型配置 JSON 字符串，可为 null
     * @return 引擎内部任务ID（engine_task_id），失败返回 null
     */
    String submitParseTask(KbFileTask task, String modelProfileJson);

    /**
     * 查询解析任务状态
     *
     * @param task 平台侧解析任务
     * @return 状态快照，不存在或查询失败返回 null
     */
    ParseTaskStatusSnapshot queryParseTaskStatus(KbFileTask task);
}
