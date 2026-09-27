// Script único e simples para as telas de login/cadastro (sem FormValidation/jQuery)
document.addEventListener('DOMContentLoaded', function() {
    console.log("✅ Script de formulário carregado");

    const loginWrapper = document.getElementById('kt_login');

    // ===== ALTERNAR ENTRE TELAS (login / cadastro / esqueci senha) =====
    function showForm(name) {
        if (!loginWrapper) return;
        loginWrapper.classList.remove('login-forgot-on', 'login-signin-on', 'login-signup-on');
        loginWrapper.classList.add('login-' + name + '-on');
    }

    const signupLink = document.getElementById('kt_login_signup');
    const forgotLink = document.getElementById('kt_login_forgot');
    const signupCancelBtn = document.getElementById('kt_login_signup_cancel');
    const forgotCancelBtn = document.getElementById('kt_login_forgot_cancel');

    if (signupLink) signupLink.addEventListener('click', function(e) { e.preventDefault(); showForm('signup'); });
    if (forgotLink) forgotLink.addEventListener('click', function(e) { e.preventDefault(); showForm('forgot'); });
    if (signupCancelBtn) signupCancelBtn.addEventListener('click', function(e) { e.preventDefault(); showForm('signin'); });
    if (forgotCancelBtn) forgotCancelBtn.addEventListener('click', function(e) { e.preventDefault(); showForm('signin'); });

    // ===== FORMULÁRIO DE CADASTRO =====
    const signupForm = document.getElementById('kt_login_signup_form');
    const signupBtn = document.getElementById('kt_login_signup_submit');

    if (signupForm && signupBtn) {
        console.log("✅ Formulário de cadastro encontrado");

        signupBtn.addEventListener('click', function(e) {
            e.preventDefault();
            console.log("🔵 Botão ENVIAR clicado");

            const username = signupForm.querySelector('input[name="username"]').value.trim();
            const email = signupForm.querySelector('input[name="email"]').value.trim();
            const password1 = signupForm.querySelector('input[name="password1"]').value;
            const password2 = signupForm.querySelector('input[name="password2"]').value;
            const agreeInput = signupForm.querySelector('input[name="agree"]');
            const agree = agreeInput ? agreeInput.checked : true;

            let erros = [];
            if (!username) erros.push('Nome é obrigatório');
            if (!email) erros.push('Email é obrigatório');
            if (!password1) erros.push('Senha é obrigatória');
            if (!password2) erros.push('Confirmação de senha é obrigatória');
            if (password1 !== password2) erros.push('Senhas não combinam');
            if (agreeInput && !agree) erros.push('Você deve aceitar os termos');

            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            if (email && !emailRegex.test(email)) erros.push('Email inválido');

            if (erros.length > 0) {
                console.log("❌ Erros de validação:", erros);
                alert('Erros encontrados:\n\n' + erros.join('\n'));
                return;
            }

            console.log("✅ Validação OK - enviando formulário...");
            signupForm.submit();
        });
    } else {
        console.log("❌ Formulário de cadastro NÃO encontrado");
    }

    // ===== FORMULÁRIO DE LOGIN =====
    const loginForm = document.getElementById('kt_login_signin_form');
    const loginBtn = document.getElementById('kt_login_signin_submit');

    if (loginForm && loginBtn) {
        console.log("✅ Formulário de login encontrado");

        loginBtn.addEventListener('click', function(e) {
            e.preventDefault();
            console.log("🔵 Botão LOGIN clicado");

            const email = loginForm.querySelector('input[name="email"]').value.trim();
            const password = loginForm.querySelector('input[name="password"]').value;

            if (!email || !password) {
                alert('Email e senha são obrigatórios');
                return;
            }

            console.log("✅ Login OK - enviando formulário...");
            loginForm.submit();
        });
    } else {
        console.log("❌ Formulário de login NÃO encontrado");
    }

    // ===== FORMULÁRIO ESQUECI A SENHA =====
    const forgotForm = document.getElementById('kt_login_forgot_form');
    const forgotSubmitBtn = document.getElementById('kt_login_forgot_submit');

    if (forgotForm && forgotSubmitBtn) {
        forgotSubmitBtn.addEventListener('click', function(e) {
            e.preventDefault();

            const email = forgotForm.querySelector('input[name="email"]').value.trim();
            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

            if (!email || !emailRegex.test(email)) {
                alert('Informe um email válido');
                return;
            }

            forgotForm.submit();
        });
    }
});
