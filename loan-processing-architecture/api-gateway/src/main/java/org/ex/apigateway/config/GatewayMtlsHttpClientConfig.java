package org.ex.apigateway.config;

import io.netty.handler.ssl.SslContext;
import io.netty.handler.ssl.SslContextBuilder;
import io.netty.handler.ssl.SslProvider;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.ssl.SslBundle;
import org.springframework.boot.ssl.SslBundles;
import org.springframework.boot.ssl.SslManagerBundle;
import org.springframework.cloud.gateway.config.HttpClientCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import javax.net.ssl.KeyManager;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.KeyManagerFactorySpi;
import javax.net.ssl.ManagerFactoryParameters;
import javax.net.ssl.TrustManager;
import javax.net.ssl.TrustManagerFactory;
import javax.net.ssl.TrustManagerFactorySpi;
import javax.net.ssl.X509ExtendedKeyManager;
import javax.net.ssl.X509ExtendedTrustManager;
import java.security.KeyStore;
import java.util.Arrays;

/**
 * Configures SPIFFE mTLS for gateway -> loan-service calls, with support for
 * SVID rotation while the process keeps running.
 *
 * SPIRE issues short-lived X.509 SVIDs (~1h) and spiffe-helper rewrites
 * /spiffe-certs partway through that TTL. Netty's SslContext is immutable once
 * built, so reading the PEM files directly at startup pinned the gateway to the
 * first SVID and every call began failing with certificate_expired an hour in.
 *
 * Instead the key/trust material now comes from a Spring SSL bundle declared
 * with reload-on-update: true, and is held behind swappable delegates
 * ({@link ReloadableX509KeyManager} / {@link ReloadableX509TrustManager}). The
 * SslContext - and therefore the HttpClient built from it - is created exactly
 * once; on rotation only the delegates are replaced, and the next TLS handshake
 * picks up the new SVID. No restart, no connection-pool churn.
 */
@Slf4j
@Configuration
public class GatewayMtlsHttpClientConfig {

    private static final String SPIFFE_BUNDLE = "spiffe";

    /**
     * Exposed as beans (rather than created inline) so the rotation behaviour
     * is reachable from tests: a test can hand in its own instances, fire a
     * bundle update, and assert the managers now serve the new certificate.
     */
    @Bean
    ReloadableX509KeyManager spiffeKeyManager() {
        return new ReloadableX509KeyManager();
    }

    @Bean
    ReloadableX509TrustManager spiffeTrustManager() {
        return new ReloadableX509TrustManager();
    }

    @Bean
    HttpClientCustomizer spiffeMtlsHttpClientCustomizer(SslBundles sslBundles,
                                                        ReloadableX509KeyManager keyManager,
                                                        ReloadableX509TrustManager trustManager) throws Exception {
        applyBundle(sslBundles.getBundle(SPIFFE_BUNDLE), keyManager, trustManager);

        // Fired by Spring's file watcher when spiffe-helper rewrites the SVID.
        sslBundles.addBundleUpdateHandler(SPIFFE_BUNDLE, updated -> {
            try {
                applyBundle(updated, keyManager, trustManager);
                log.info("SPIFFE SVID rotated - gateway mTLS material reloaded without restart");
            } catch (Exception ex) {
                // Deliberately swallowed: the previous delegates stay in place,
                // so a malformed mid-write read degrades to "keep using the
                // still-valid old SVID" instead of tearing down outbound mTLS.
                log.error("Failed to reload rotated SPIFFE material; keeping previous key/trust managers", ex);
            }
        });

        SslContext sslContext = SslContextBuilder.forClient()
                // Pin to the pure-JDK provider. Netty otherwise silently
                // prefers the native BoringSSL/tcnative engine when it's on
                // the classpath (pulled in transitively by reactor-netty-http),
                // which has known PKIX path-building inconsistencies against
                // SPIFFE X.509 SVIDs (empty-subject leaf certs, EC keys).
                // Pinning removes that ambiguity entirely.
                .sslProvider(SslProvider.JDK)
                .keyManager(new SingletonKeyManagerFactory(keyManager))
                .trustManager(new SingletonTrustManagerFactory(trustManager))
                .build();

        log.info("SPIFFE mTLS SSL context configured for gateway -> loan-service calls (hot-reloadable)");
        return httpClient -> httpClient.secure(ssl -> ssl.sslContext(sslContext));
    }

    /**
     * Points the swappable delegates at the managers Spring built from the
     * current PEM files. Spring does the PEM parsing and PKIX TrustManager
     * construction, so a malformed or empty bundle surfaces as a real,
     * readable exception here rather than an opaque SSLHandshakeException at
     * connection time.
     */
    private static void applyBundle(SslBundle bundle,
                                    ReloadableX509KeyManager keyManager,
                                    ReloadableX509TrustManager trustManager) throws Exception {
        // Validate BEFORE swapping. A torn read - the watcher firing while
        // spiffe-helper is still writing - yields a bundle that parses fine but
        // carries no key entries. That would not throw, so without this check
        // the swap would succeed and silently replace a working SVID with an
        // empty key manager, leaving the gateway unable to present a client
        // certificate until the next rotation.
        requireNonEmpty(bundle.getStores().getKeyStore(), "key");
        requireNonEmpty(bundle.getStores().getTrustStore(), "trust");

        SslManagerBundle managers = bundle.getManagers();
        X509ExtendedKeyManager newKeyManager = firstX509KeyManager(managers.getKeyManagerFactory());
        X509ExtendedTrustManager newTrustManager = firstX509TrustManager(managers.getTrustManagerFactory());

        // Both resolved cleanly - only now is it safe to swap.
        keyManager.setDelegate(newKeyManager);
        trustManager.setDelegate(newTrustManager);
    }

    private static void requireNonEmpty(KeyStore store, String kind) throws Exception {
        if (store == null || !store.aliases().hasMoreElements()) {
            throw new IllegalStateException(
                    "SPIFFE bundle contained no " + kind + " entries - refusing to swap in empty material");
        }
    }

    private static X509ExtendedKeyManager firstX509KeyManager(KeyManagerFactory factory) {
        return Arrays.stream(factory.getKeyManagers())
                .filter(X509ExtendedKeyManager.class::isInstance)
                .map(X509ExtendedKeyManager.class::cast)
                .findFirst()
                .orElseThrow(() -> new IllegalStateException(
                        "SPIFFE bundle produced no X509ExtendedKeyManager - is svid.pem/svid_key.pem present?"));
    }

    private static X509ExtendedTrustManager firstX509TrustManager(TrustManagerFactory factory) {
        return Arrays.stream(factory.getTrustManagers())
                .filter(X509ExtendedTrustManager.class::isInstance)
                .map(X509ExtendedTrustManager.class::cast)
                .findFirst()
                .orElseThrow(() -> new IllegalStateException(
                        "SPIFFE trust bundle produced no X509ExtendedTrustManager - is bundle.pem present and non-empty?"));
    }

    /**
     * Netty's SslContextBuilder only accepts a KeyManagerFactory, not a bare
     * KeyManager, so this adapts our single swappable manager into one.
     */
    private static final class SingletonKeyManagerFactory extends KeyManagerFactory {
        private SingletonKeyManagerFactory(KeyManager keyManager) {
            super(new KeyManagerFactorySpi() {
                @Override
                protected void engineInit(KeyStore keyStore, char[] password) {
                    // No-op: the delegate is supplied directly.
                }

                @Override
                protected void engineInit(ManagerFactoryParameters parameters) {
                    // No-op: the delegate is supplied directly.
                }

                @Override
                protected KeyManager[] engineGetKeyManagers() {
                    return new KeyManager[] { keyManager };
                }
            }, null, KeyManagerFactory.getDefaultAlgorithm());
        }
    }

    private static final class SingletonTrustManagerFactory extends TrustManagerFactory {
        private SingletonTrustManagerFactory(TrustManager trustManager) {
            super(new TrustManagerFactorySpi() {
                @Override
                protected void engineInit(KeyStore keyStore) {
                    // No-op: the delegate is supplied directly.
                }

                @Override
                protected void engineInit(ManagerFactoryParameters parameters) {
                    // No-op: the delegate is supplied directly.
                }

                @Override
                protected TrustManager[] engineGetTrustManagers() {
                    return new TrustManager[] { trustManager };
                }
            }, null, TrustManagerFactory.getDefaultAlgorithm());
        }
    }
}
