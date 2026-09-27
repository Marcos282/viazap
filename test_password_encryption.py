#!/usr/bin/env python
"""
Script para testar se as senhas estão sendo criptografadas corretamente
"""

import os
import sys
import django

# Configurar o Django
sys.path.append('/home/marcos/Documentos/projetos/burger')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'burger.settings')
django.setup()

from customers.models import User

def testar_criptografia_senhas():
    print("🔐 TESTE DE CRIPTOGRAFIA DE SENHAS")
    print("="*50)
    
    # Buscar todos os usuários
    usuarios = User.objects.all()
    print(f"📊 Total de usuários: {usuarios.count()}")
    
    for user in usuarios:
        print(f"\n👤 Usuário: {user.username}")
        print(f"   Email: {user.email}")
        print(f"   Hash da senha: {user.password[:50]}...")
        print(f"   Tamanho do hash: {len(user.password)} caracteres")
        
        # Verificar se a senha está criptografada (hash Django começa com algoritmo)
        if user.password.startswith(('pbkdf2_sha256$', 'argon2$', 'bcrypt$')):
            print(f"   ✅ Senha está CRIPTOGRAFADA corretamente")
            
            # Tentar verificar uma senha conhecida
            if user.username == 'sofia':
                # Vamos tentar algumas senhas comuns para teste
                senhas_teste = ['mariola123', '123456', 'senha123']
                for senha in senhas_teste:
                    if user.check_password(senha):
                        print(f"   🔑 Senha atual é: {senha}")
                        break
                else:
                    print(f"   🔐 Senha não é nenhuma das testadas")
                    
        elif user.password == '' or user.password is None:
            print(f"   ⚠️  Usuário SEM SENHA definida")
        else:
            print(f"   ❌ PERIGO: Senha pode estar em TEXTO PLANO!")
            print(f"      Conteúdo: {user.password}")
    
    print("\n" + "="*50)
    print("🔍 VERIFICAÇÃO COMPLETA")

if __name__ == "__main__":
    testar_criptografia_senhas()