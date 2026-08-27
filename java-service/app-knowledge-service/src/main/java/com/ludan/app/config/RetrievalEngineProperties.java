package com.ludan.app.config;

import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * 对接 app-rag-doc（retrieve-service）检索能力。
 * <p>
 * **契约以《当前代码接口完整文档》为准**（{@code POST /api/v1/retrieve/query}，请求体含 {@code kb_id}、{@code query}、{@code options.profile} 等）。
 * 《JAVA与AI引擎对接接口》§3.7 使用 {@code collection_ids} 的旧约定已由本文档替代，仅作历史参考。
 *
 * @author ludan
 */
@Getter
@Setter
@Component
@ConfigurationProperties(prefix = "retrieval-engine")
public class RetrievalEngineProperties {

    /** 服务启用时走 Feign 调用 app-rag-doc；为 false 时搜文件不请求远端 */
    private boolean enabled = true;

    /** Nacos 注册服务名。解析和检索实际是同一个 AI 引擎微服务。 */
    private String serviceName = "app-rag-doc";

    /**
     * 当 retrieve-service 配置了 {@code DANBAO_API_TOKEN} 时，通过该头传递（见《当前代码接口完整文档》§1）。
     */
    private String apiToken = "";

    /**
     * 检索选项 profile，文档建议显式传入，默认 {@code business_plan}。
     */
    private String defaultProfile = "general_document";

    /**
     * 默认每条请求的 {@code top_k}（文档默认 5，此处略放大便于跨文件聚合）
     */
    private int defaultTopK = 40;

    /** 为 true 时调用 {@code POST /api/v1/retrieve}，为 false 时调用 {@code POST /api/v1/retrieve/query} */
    private boolean compatRetrievePath = false;

    /** 文件索引接口默认是否异步。 */
    private boolean indexAsyncMode = true;

    /** 注入大模型 system prompt 的检索上下文总字符预算。 */
    private int contextMaxChars = 16000;

    /** ES Chunk 原文预算占比。 */
    private double textContextRatio = 0.50D;

    /** 局部实体关系预算占比。 */
    private double graphContextRatio = 0.35D;

    /** 社区报告/全局图摘要预算占比。 */
    private double communityContextRatio = 0.15D;
}
