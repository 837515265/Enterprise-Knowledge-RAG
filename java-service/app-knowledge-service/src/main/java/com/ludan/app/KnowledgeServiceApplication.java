package com.ludan.app;

import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.client.discovery.EnableDiscoveryClient;
import org.springframework.cloud.openfeign.EnableFeignClients;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * 知识库管理平台微服务启动类。
 *
 * @author ludan
 */
@Slf4j
@EnableDiscoveryClient
@EnableFeignClients(basePackages = {"com.ludan", "com.central"})
@SpringBootApplication(scanBasePackages = {"com.ludan", "com.central"})
@EnableAsync
@EnableScheduling
public class KnowledgeServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(KnowledgeServiceApplication.class, args);
    }
}
