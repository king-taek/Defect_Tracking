"""nav 라우트 페이지.

FluentWindow 의 NavigationInterface 에 붙는 6개 페이지가 여기 모인다(REVIEW-01 P5).
모달 시트·다이얼로그는 `app/ui/sheets/` 로 간다.

각 페이지는 고유한 setObjectName 을 자기 __init__ 에서 지정한다. 호출부에 맡기면 빠뜨리기
쉽고, objectName 이 곧 라우트 키라 비면 ValueError, 겹치면 라우팅이 깨진다.
"""
