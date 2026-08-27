package com.ludan.app.config;

import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * 解析引擎配置属性。
 *
 * @author ludan
 */
@Getter
@Setter
@Component
@ConfigurationProperties(prefix = "parse-engine")
public class ParseEngineProperties {

    /** Nacos 注册服务名。解析和检索实际是同一个 AI 引擎微服务。 */
    private String serviceName = "app-rag-doc";

    /** 当 AI 引擎启用 DANBAO_API_TOKEN 时传递。 */
    private String apiToken = "";

    /** 默认文档 profile。未能从模型配置解析时使用 auto。 */
    private String defaultProfile = "auto";

    /** 是否启用解析引擎调用，false 时仅落库不调用引擎 */
    private boolean enabled = true;

    /** 是否启用任务状态轮询 */
    private boolean pollEnabled = true;

    /** 轮询初始延迟（毫秒） */
    private long pollInitialDelayMs = 10000L;

    /** 轮询固定间隔（毫秒） */
    private long pollFixedDelayMs = 10000L;

    /** 单次轮询批量任务数 */
    private int pollBatchSize = 20;
}
