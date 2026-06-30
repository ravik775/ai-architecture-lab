package org.ex.apigateway.controller;

import org.ex.apigateway.FallbackResponse;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/fallback")
public class FallbackController {

    @GetMapping("/loan-service")
    public ResponseEntity<FallbackResponse> loanServiceFallback() {

        FallbackResponse response = new FallbackResponse(
                "LOAN_SERVICE_UNAVAILABLE",
                "Loan Service is temporarily unavailable.",
                System.currentTimeMillis()
        );

        return ResponseEntity
                .status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(response);
    }
}