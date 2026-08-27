package com.ludan.app.config;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestTemplate;

@Configuration
public class StreamHttpClientConfig {

    @Value("${llm.connect-timeout}")
    private int connectTimeout;

    @Value("${llm.read-timeout}")
    private int readTimeout;

    @Bean
    @LoadBalanced
    public RestTemplate loadBalancedStreamRestTemplate() {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(connectTimeout);
        factory.setReadTimeout(readTimeout);
        factory.setBufferRequestBody(false);
        return new RestTemplate(factory);
    }
}

