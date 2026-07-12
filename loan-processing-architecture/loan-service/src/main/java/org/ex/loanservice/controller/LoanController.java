package org.ex.loanservice.controller;

import lombok.Getter;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/loan")
public class LoanController {

    @GetMapping()
    ResponseEntity<String> get(){
        return ResponseEntity.ok("This is from Loan SErvice");
    }
}
