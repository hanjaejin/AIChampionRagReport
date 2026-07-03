# file: conftest.py
"""pytest가 프로젝트 루트를 sys.path에 추가하도록 하는 앵커 파일.

루트에 conftest.py가 있으면 `pytest`를 어느 방식으로 실행해도
루트 모듈(chunker 등)을 임포트할 수 있다.
"""
