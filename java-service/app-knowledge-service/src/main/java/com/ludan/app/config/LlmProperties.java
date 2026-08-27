package com.ludan.app.config;

import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * 大模型代理调用配置
 *
 * @author ludan
 */
@Getter
@Setter
@Component
@ConfigurationProperties(prefix = "llm")
public class LlmProperties {

    /** 内部代理三方应用ID（common_proxy.app_info.app_id） */
    private String thirdAppId = "NEW_API";

    /** 内部代理三方接口ID（common_proxy.app_third_config.interface_id） */
    private String thirdInterfaceId = "chat-completions";

    /** 调用方应用ID（common_proxy.app_info.app_id） */
    private String applyAppId = "APP_KNOWLEDGE_SERVICE";

    /** 目标接口路径（域名后部分），例如 /v1/chat/completions */
    private String thirdUrl = "/v1/chat/completions";

    /** new-api 鉴权 key */
    private String apiKey;

    /** 知识库未配置模型时使用的默认模型，由配置文件提供 */
    private String defaultModel;

    /** 连接超时（毫秒） */
    private int connectTimeout = 5000;

    /** 读取超时（毫秒） */
    private int readTimeout = 120000;
}
