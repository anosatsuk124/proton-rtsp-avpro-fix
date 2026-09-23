.intel_syntax noprefix
.text
.global live_network_body
live_network_body:
    movzx eax, WORD PTR [rbx+0x80]
    cmp eax, 1
    jne done
    movabs rdx, 0x7ff0000000000000
    cmp QWORD PTR [rbx+0x70], rdx
    jne done
    mov eax, 2
done:
    add rsp, 0x38
    pop rbx
    pop rbp
    ret
