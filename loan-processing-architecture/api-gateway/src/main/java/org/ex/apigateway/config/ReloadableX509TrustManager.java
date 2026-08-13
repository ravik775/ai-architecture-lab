package org.ex.apigateway.config;

import javax.net.ssl.SSLEngine;
import javax.net.ssl.X509ExtendedTrustManager;
import java.net.Socket;
import java.security.cert.CertificateException;
import java.security.cert.X509Certificate;

/**
 * Trust-manager counterpart to {@link ReloadableX509KeyManager}. Swapping the
 * delegate lets the gateway pick up a rotated SPIRE trust bundle - which
 * matters independently of the SVID, because the bundle changes whenever the
 * SPIRE server rotates its CA.
 */
public final class ReloadableX509TrustManager extends X509ExtendedTrustManager {

    private volatile X509ExtendedTrustManager delegate;

    public void setDelegate(X509ExtendedTrustManager delegate) {
        this.delegate = delegate;
    }

    @Override
    public void checkClientTrusted(X509Certificate[] chain, String authType) throws CertificateException {
        delegate.checkClientTrusted(chain, authType);
    }

    @Override
    public void checkClientTrusted(X509Certificate[] chain, String authType, Socket socket) throws CertificateException {
        delegate.checkClientTrusted(chain, authType, socket);
    }

    @Override
    public void checkClientTrusted(X509Certificate[] chain, String authType, SSLEngine engine) throws CertificateException {
        delegate.checkClientTrusted(chain, authType, engine);
    }

    @Override
    public void checkServerTrusted(X509Certificate[] chain, String authType) throws CertificateException {
        delegate.checkServerTrusted(chain, authType);
    }

    @Override
    public void checkServerTrusted(X509Certificate[] chain, String authType, Socket socket) throws CertificateException {
        delegate.checkServerTrusted(chain, authType, socket);
    }

    @Override
    public void checkServerTrusted(X509Certificate[] chain, String authType, SSLEngine engine) throws CertificateException {
        delegate.checkServerTrusted(chain, authType, engine);
    }

    @Override
    public X509Certificate[] getAcceptedIssuers() {
        return delegate.getAcceptedIssuers();
    }
}
