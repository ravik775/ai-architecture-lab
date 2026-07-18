package org.ex.loanservice.controller;

import jakarta.ws.rs.DefaultValue;
import lombok.Getter;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/loan")
public class LoanController {

    @GetMapping()
    ResponseEntity<String> get(@RequestParam("from") @DefaultValue("Guest") String from){
        return ResponseEntity.ok("This is from Loan SErvice: From "+ from);
    }
}
