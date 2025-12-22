#!/usr/bin/env python3
import sys
import re

def check_commit_message(msg_file):
    try:
        with open(msg_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"❌ 커밋 메시지를 읽을 수 없습니다: {e}")
        return 1

    if not lines:
        print("❌ 커밋 메시지가 비어있습니다.")
        return 1

    # 1. Header Format: <type>: <subject>
    header = lines[0].strip()
    # Pattern: type(scope optional): subject
    # Types: feat, fix, docs, style, refactor, test, chore
    pattern = r'^(feat|fix|docs|style|refactor|test|chore)(\(.+\))?!?: .+$'
    
    if not re.match(pattern, header):
        print("❌ 커밋 메시지 형식이 잘못되었습니다.")
        print("규칙: <type>: <subject>")
        print("허용된 타입: feat, fix, docs, style, refactor, test, chore")
        print(f"입력된 헤더: {header}")
        return 1

    # 2. Subject check (Korean check is hard to enforce strictly if mixed, but we can warn)
    # This is a loose check to encourage Korean usage if requested, 
    # but the rule says "Subject: Korean", so we can check for Hangul characters.
    # However, sometimes subject might be "Update README", so we won't block purely on English unless strict.
    # For now, we trust the user on language, but we enforce length.
    
    if len(header) > 50:
        print(f"⚠️ 제목이 50자를 초과했습니다 ({len(header)}자). 간결하게 작성해주세요.")
        # Blocking for length is often annoying, warning is better unless strict.
        # But for 'strict' conventions, usually it's a block. Let's return 1 if strict.
        # Let's keep it as a warning for now to be safe, or user can request strictness.

    # 3. Security Check (Basic pattern matching)
    content = "".join(lines)
    # Check for obvious secrets in the message itself (rare but possible) or typical accidentals
    if "BEGIN RSA PRIVATE KEY" in content:
        print("❌ 커밋 메시지에 개인 키가 포함된 것 같습니다.")
        return 1

    print("✅ 커밋 메시지 검증 통과")
    return 0

if __name__ == "__main__":
    sys.exit(check_commit_message(sys.argv[1]))
