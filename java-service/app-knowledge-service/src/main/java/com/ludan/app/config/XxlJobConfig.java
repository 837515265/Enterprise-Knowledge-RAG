package com.ludan.app.config;

import com.xxl.job.core.executor.impl.XxlJobSpringExecutor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * XXL-JOB 执行器配置（与 AI Center 等微服务通用能力对齐）。
 *
 * @author breathe
 */
@Configuration
public class XxlJobConfig {
    @Value("${xxl.job.admin-addresses}")
    private String adminAddress;
    @Value("${xxl.job.executor.appname}")
    private String appname;
    @Value("${xxl.job.executor.ip}")
    private String ip;
    @Value("${xxl.job.executor.log-path}")
    private String logPath;
    @Value("${xxl.job.executor.log-retention-days}")
    private Integer logRetentionDays;
    @Value("${xxl.job.executor.address}")
    private String address;
    @Value("${xxl.job.access-token}")
    private String accessToken;

    @Bean
    public XxlJobSpringExecutor xxlJobSpringExecutor() {
        XxlJobSpringExecutor executor = new XxlJobSpringExecutor();
        executor.setIp(ip);
        executor.setLogPath(logPath);
        executor.setAdminAddresses(adminAddress);
        executor.setAppname(appname);
        executor.setLogRetentionDays(logRetentionDays);
        executor.setAddress(address);
        executor.setAccessToken(accessToken);
        return executor;
    }
}
