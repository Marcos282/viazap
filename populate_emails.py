#!/usr/bin/env python
"""
Script para popular emails dos usuários existentes
"""

import os
import sys
import django

# Configurar o Django
sys.path.append('/home/marcos/Documentos/projetos/burger')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'burger.settings')
django.setup()

from customers.models import User

def atualizar_emails():
    print("🔄 Atualizando emails dos usuários...")
    
    usuarios = User.objects.all()
    for user in usuarios:
        if not user.email or user.email == '':
            # Criar email baseado no username
            novo_email = f"{user.username}@example.com"
            user.email = novo_email
            user.save()
            print(f"   ✅ {user.username} -> {novo_email}")
        else:
            print(f"   ⏭️  {user.username} já tem email: {user.email}")
    
    print("✅ Emails atualizados com sucesso!")

if __name__ == "__main__":
    atualizar_emails()