package org.ex.apigateway.config;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import javax.net.ssl.SSLEngine;
import javax.net.ssl.X509ExtendedTrustManager;
import java.net.Socket;
import java.security.cert.CertificateException;
import java.security.cert.X509Certificate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * The trust manager rotates independently of the SVID: SPIRE rotates its CA on
 * its own schedule, so the gateway must be able to pick up a new bundle.pem
 * without a restart even when its own certificate is unchanged.
 */
class ReloadableX509TrustManagerTest {

    private X509ExtendedTrustManager oldDelegate;
    private X509ExtendedTrustManager newDelegate;
    private ReloadableX509TrustManager trustManager;
    private X509Certificate[] chain;
    // Real mock instances rather than nulls: Mockito's any(Type.class) matchers
    // deliberately do not match null, and a live SSLEngine/Socket is closer to
    // what the JSSE handshake actually passes in.
    private SSLEngine engine;
    private Socket socket;

    @BeforeEach
    void setUp() {
        oldDelegate = mock(X509ExtendedTrustManager.class);
        newDelegate = mock(X509ExtendedTrustManager.class);
        trustManager = new ReloadableX509TrustManager();
        trustManager.setDelegate(oldDelegate);
        chain = new X509Certificate[] { mock(X509Certificate.class) };
        engine = mock(SSLEngine.class);
        socket = mock(Socket.class);
    }

    @Test
    void checkServerTrustedWithEngine_isDelegated() throws Exception {
        // Scenario: the SSLEngine overload is the one reactor-netty invokes
        // when validating loan-service's server certificate. Missing it would
        // fall through to X509ExtendedTrustManager's default, which throws
        // UnsupportedOperationException at handshake time.
        trustManager.checkServerTrusted(chain, "ECDHE_ECDSA", engine);

        verify(oldDelegate).checkServerTrusted(any(), any(), any(SSLEngine.class));
    }

    @Test
    void swappingDelegate_redirectsValidationToTheNewTrustBundle() throws Exception {
        // Scenario: SPIRE rotated its CA and spiffe-helper rewrote bundle.pem.
        // Validation must immediately consult the new bundle - continuing to
        // trust only the old CA would reject every peer presenting a cert
        // signed by the new one.
        trustManager.setDelegate(newDelegate);

        trustManager.checkServerTrusted(chain, "ECDHE_ECDSA", engine);

        verify(newDelegate).checkServerTrusted(any(), any(), any(SSLEngine.class));
        verify(oldDelegate, never()).checkServerTrusted(any(), any(), any(SSLEngine.class));
    }

    @Test
    void certificateException_propagatesRatherThanBeingSwallowed() {
        // Scenario: an untrusted peer must stay untrusted. A delegating wrapper
        // that accidentally caught CertificateException would turn a failed
        // trust check into a silent success - i.e. it would disable peer
        // verification entirely, which is the worst possible failure mode here.
        assertThatThrownBy(() -> {
            doThrow(new CertificateException("untrusted"))
                    .when(oldDelegate).checkServerTrusted(any(), any(), any(SSLEngine.class));
            trustManager.checkServerTrusted(chain, "ECDHE_ECDSA", engine);
        }).isInstanceOf(CertificateException.class).hasMessage("untrusted");
    }

    @Test
    void acceptedIssuers_comeFromTheCurrentDelegate() {
        // Scenario: after a CA rotation the advertised issuer list must reflect
        // the new bundle, since it is what the peer uses to pick a chain.
        X509Certificate[] newIssuers = new X509Certificate[] { mock(X509Certificate.class) };
        when(newDelegate.getAcceptedIssuers()).thenReturn(newIssuers);

        trustManager.setDelegate(newDelegate);

        assertThat(trustManager.getAcceptedIssuers()).isSameAs(newIssuers);
    }

    @Test
    void remainingTrustManagerMethods_areDelegated() throws Exception {
        // Scenario: completeness of the X509ExtendedTrustManager contract - the
        // client-side and Socket overloads are unused by the gateway today but
        // must not be left as unimplemented holes.
        trustManager.checkClientTrusted(chain, "ECDHE_ECDSA");
        trustManager.checkClientTrusted(chain, "ECDHE_ECDSA", socket);
        trustManager.checkClientTrusted(chain, "ECDHE_ECDSA", engine);
        trustManager.checkServerTrusted(chain, "ECDHE_ECDSA");
        trustManager.checkServerTrusted(chain, "ECDHE_ECDSA", socket);

        verify(oldDelegate).checkClientTrusted(chain, "ECDHE_ECDSA");
        verify(oldDelegate).checkClientTrusted(any(), any(), any(Socket.class));
        verify(oldDelegate).checkClientTrusted(any(), any(), any(SSLEngine.class));
        verify(oldDelegate).checkServerTrusted(chain, "ECDHE_ECDSA");
        verify(oldDelegate).checkServerTrusted(any(), any(), any(Socket.class));
    }
}
