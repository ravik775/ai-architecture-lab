package org.ex.apigateway.config;

import io.netty.handler.ssl.SslContext;
import io.netty.handler.ssl.SslContextBuilder;
import io.netty.handler.ssl.SslProvider;
import lombok.extern.slf4j.Slf4j;
import org.springframework.cloud.gateway.config.HttpClientCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import javax.net.ssl.TrustManagerFactory;
import java.io.File;
import java.io.FileInputStream;
import java.security.KeyStore;
import java.security.cert.Certificate;
import java.security.cert.CertificateFactory;
import java.util.Collection;

@Slf4j
@Configuration
public class GatewayMtlsHttpClientConfig {

    private static final String CERT_DIR = "/spiffe-certs";

    @Bean
    HttpClientCustomizer spiffeMtlsHttpClientCustomizer() {
        return httpClient -> httpClient.secure(ssl -> {
            try {
                log.info("Loading SPIFFE mTLS materials from {}", CERT_DIR);

                TrustManagerFactory trustManagerFactory =
                        buildTrustManagerFactory(new File(CERT_DIR, "bundle.pem"));

                SslContext sslContext = SslContextBuilder.forClient()
                        // Pin to the pure-JDK provider. Netty otherwise silently
                        // prefers the native BoringSSL/tcnative engine when it's on
                        // the classpath (pulled in transitively by reactor-netty-http),
                        // which has known PKIX path-building inconsistencies against
                        // SPIFFE X.509 SVIDs (empty-subject leaf certs, EC keys).
                        // Pinning removes that ambiguity entirely.
                        .sslProvider(SslProvider.JDK)
                        .keyManager(
                                new File(CERT_DIR, "svid.pem"),
                                new File(CERT_DIR, "svid_key.pem"))
                        .trustManager(trustManagerFactory)
                        .build();

                ssl.sslContext(sslContext);
                log.info("SPIFFE mTLS SSL context configured for gateway -> loan-service calls");
            } catch (Exception ex) {
                log.error("Failed to configure SPIFFE mTLS for gateway", ex);
                throw new IllegalStateException("Failed to configure SPIFFE mTLS for Gateway", ex);
            }
        });
    }

    /**
     * Builds a PKIX TrustManagerFactory directly from the SPIRE trust bundle
     * instead of handing the raw File to Netty's trustManager(File) overload.
     * This guarantees standard JDK X.509 path-validation semantics and throws
     * a real, readable exception if the bundle is empty/unparseable, rather
     * than the opaque SSLHandshakeException you get from the provider-auto-
     * selected path.
     */
    private TrustManagerFactory buildTrustManagerFactory(File bundleFile) throws Exception {
        CertificateFactory certificateFactory = CertificateFactory.getInstance("X.509");
        Collection<? extends Certificate> caCerts;
        try (FileInputStream in = new FileInputStream(bundleFile)) {
            caCerts = certificateFactory.generateCertificates(in);
        }

        if (caCerts.isEmpty()) {
            throw new IllegalStateException(
                    "SPIFFE trust bundle at " + bundleFile + " contained no certificates");
        }

        KeyStore trustStore = KeyStore.getInstance(KeyStore.getDefaultType());
        trustStore.load(null, null);
        int i = 0;
        for (Certificate cert : caCerts) {
            trustStore.setCertificateEntry("spire-ca-" + (i++), cert);
        }

        TrustManagerFactory trustManagerFactory =
                TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm()); // PKIX
        trustManagerFactory.init(trustStore);
        return trustManagerFactory;
    }
}