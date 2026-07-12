package org.ex.apigateway.service;
import org.ex.apigateway.model.TenantPolicy;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class TenantPolicyService {
    private final RedisTemplate<String, TenantPolicy> template;
    public TenantPolicyService(RedisTemplate<String, TenantPolicy> template){
        this.template = template;
    }

    protected TenantPolicy getDefault(String tenant){
        TenantPolicy policy = new TenantPolicy();
        policy.setTenantId(tenant);
        policy.setRequestsPerMinute(10);
        policy.setBurstCapacity(8);
        return policy;
    }

    public TenantPolicy getPolicy(String tenant){
        String key = "tenant:policy:"+tenant;
        var val = template.opsForValue().get(key);
        if (val == null){
            return getDefault(tenant);
        }
        return val;
    }


}
