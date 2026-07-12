package org.ex.apigateway.model;

import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
public class TenantPolicy {
    private String tenantId;
    private long requestsPerMinute;
    private long burstCapacity;
}