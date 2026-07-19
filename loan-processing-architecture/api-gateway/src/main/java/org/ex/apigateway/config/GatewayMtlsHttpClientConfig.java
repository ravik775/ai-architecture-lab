package org.ex.apigateway.config;
import io.netty.handler.ssl.util.InsecureTrustManagerFactory;
import io.netty.handler.ssl.SslContext;
import io.netty.handler.ssl.SslContextBuilder;
import org.springframework.cloud.gateway.config.HttpClientCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.io.File;
import reactor.netty.http.client.HttpClient;
import io.netty.handler.logging.LogLevel;
import reactor.netty.http.client.HttpClient;
import reactor.netty.transport.logging.AdvancedByteBufFormat;
@Configuration
public class GatewayMtlsHttpClientConfig {

    //@Bean
    public HttpClient httpClient() {
        return HttpClient.create()
                .wiretap(
                        "reactor.netty.http.client.HttpClient",
                        LogLevel.DEBUG,
                        AdvancedByteBufFormat.TEXTUAL
                );
    }

    @Bean
    HttpClientCustomizer spiffeMtlsHttpClientCustomizer() {
        System.out.println(">>> SPIFFE MTLS CUSTOMIZER EXECUTED <<<");

        return httpClient -> httpClient.secure(ssl -> {
            try {
                System.out.println(">>> LOADING SPIFFE CERTS <<<");
                SslContext sslContext = SslContextBuilder.forClient()
                        .keyManager(
                                new File("/spiffe-certs/svid.pem"),
                                new File("/spiffe-certs/svid_key.pem"))
                         //TODO: .trustManager(new File("/spiffe-certs/bundle.pem"))
                        .trustManager(InsecureTrustManagerFactory.INSTANCE)
                        .build();

                ssl.sslContext(sslContext);
                System.out.println(">>> SPIFFE SSL CONTEXT CONFIGURED <<<");
            } catch (Exception ex) {
                System.out.println(">>> SPIFFE SSL CONTEXT Failed to configure SPIFFE mTLS for Gateway <<<");
                ex.printStackTrace();
                throw new IllegalStateException("Failed to configure SPIFFE mTLS for Gateway", ex);
            }
        });
    }
}