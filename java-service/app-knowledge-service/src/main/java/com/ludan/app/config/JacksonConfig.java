package com.ludan.app.config;

import com.fasterxml.jackson.databind.ser.std.ToStringSerializer;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.text.DateFormat;
import java.text.SimpleDateFormat;
import java.util.TimeZone;

/**
 * Jackson 序列化配置。
 *
 * @author GPT-5.4
 */
@Configuration
public class JacksonConfig {

    private static final String DEFAULT_DATE_TIME_PATTERN = "yyyy-MM-dd HH:mm:ss";
    private static final TimeZone DEFAULT_TIME_ZONE = TimeZone.getTimeZone("Asia/Shanghai");

    /**
     * 统一 JSON 序列化规则：Long 转字符串，Date 转本地时间字符串。
     *
     * @return Jackson 自定义配置
     */
    @Bean
    public Jackson2ObjectMapperBuilderCustomizer jackson2ObjectMapperBuilderCustomizer() {
        return builder -> {
            builder.serializerByType(Long.class, ToStringSerializer.instance);
            builder.serializerByType(Long.TYPE, ToStringSerializer.instance);
            builder.timeZone(DEFAULT_TIME_ZONE);
            builder.dateFormat(defaultDateFormat());
        };
    }

    /**
     * 创建日期格式化器，避免 Date 默认输出 ISO-8601 UTC 偏移格式。
     *
     * @return 日期格式化器
     */
    private DateFormat defaultDateFormat() {
        DateFormat dateFormat = new SimpleDateFormat(DEFAULT_DATE_TIME_PATTERN);
        dateFormat.setTimeZone(DEFAULT_TIME_ZONE);
        return dateFormat;
    }
}
