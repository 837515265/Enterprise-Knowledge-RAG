package com.ludan.app.config;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.concurrent.*;

/**
 * 线程池配置
 * @Author: breathe
 * @CreateTime: 2025-03-14
 */
@Configuration
@Slf4j
@RequiredArgsConstructor
public class ThreadPoolConfig {
    @Bean
    public ScheduledExecutorService getThreadPool() {
        return Executors.newSingleThreadScheduledExecutor();
    }
}