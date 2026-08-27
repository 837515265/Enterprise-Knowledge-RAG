FROM swr.cn-north-4.myhuaweicloud.com/sdndapps/ldsk-java8-centos7:1.4

RUN sed -i 's/securerandom.source=file:\/dev\/random/securerandom.source=file:\/dev\/.\/urandom/g' /usr/local/jdk/jre/lib/security/java.security

RUN groupadd --gid 1000 appuser && useradd --home-dir /home/appuser --create-home --uid 1000 --gid 1000 --shell /bin/sh --skel /dev/null appuser
USER appuser
ENV LANG en_US.utf8
WORKDIR /home/appuser/app

# 修改为各自服务的 target 路径、jar 包名
COPY app-knowledge-service/target/libs ./libs
COPY app-knowledge-service/target/resources ./resources
COPY app-knowledge-service/target/ldsk-libs ./ldsk-libs
COPY app-knowledge-service/target/app-knowledge-service.jar ./
ENTRYPOINT  java ${JVM_OPTS} -cp "*:libs/*:ldsk-libs/*:resources" com.ludan.app.KnowledgeServiceApplication ${SPRING_OPTS}
EXPOSE 20743