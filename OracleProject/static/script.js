// [수정] Flask 템플릿으로부터 상태를 전달받도록 파라미터 추가
function updateAuthLink(isLoggedIn, username) {
    const authLinkElement = document.getElementById('auth-link');
    if (!authLinkElement) return;

    // [변경] localStorage 대신 Flask에서 전달받은 isLoggedIn 사용
    if (isLoggedIn === true) {
        // 로그인 상태: '마이페이지'와 '로그아웃'을 표시합니다.
        // [변경] URL은 Flask 라우트에 맞게 수정하거나 하드코딩된 경로 사용
        authLinkElement.innerHTML = `
            <a href="/mypage">마이페이지</a>
            <span class="separator">|</span> 
            <a href="#" id="logout-btn">로그아웃</a> 
        `;
        
        // 로그아웃 버튼에 이벤트 리스너를 추가합니다.
        const logoutBtn = document.getElementById('logout-btn');
        if (logoutBtn) {
            // [유지] 로그아웃 이벤트는 AJAX 처리 함수로 연결
            logoutBtn.addEventListener('click', handleLogout);
        }

    } else {
        // 로그아웃 상태: "로그인"만 표시합니다.
        // [변경] URL은 Flask 라우트에 맞게 수정
        authLinkElement.innerHTML = '<a href="/login">로그인</a>';
    }
}

// [수정] 로그아웃 처리 함수 (Flask 백엔드와 비동기 통신)
async function handleLogout(event) {
    event.preventDefault(); 
    
    // [변경] 서버에 로그아웃 요청을 보냅니다.
    try {
        const response = await fetch('/logout', { method: 'POST' });
        
        if (response.ok) { // HTTP 상태 코드가 200-299인 경우
            alert('로그아웃 되었습니다.');
            // 로그아웃 후 메인 페이지로 이동 (서버 응답에 따라)
            window.location.href = '/'; 
        } else {
            // 서버에서 실패 응답을 보낸 경우
            const errorData = await response.json();
            alert('로그아웃 실패: ' + (errorData.message || '알 수 없는 오류'));
        }
    } catch (error) {
        console.error('Logout failed:', error);
        alert('서버 통신 오류로 로그아웃에 실패했습니다.');
    }
}

// [수정] 로그인 폼 제출 처리 (클라이언트 측 시뮬레이션 제거)
function handleLogin(event) {
    // [변경] AJAX 로그인을 원한다면 event.preventDefault()를 사용해야 하지만,
    // 현재 Flask 폼 제출(POST)을 그대로 사용하도록 이 함수는 비활성화합니다.
    
    // Flask는 폼을 제출받고 서버 측에서 인증 후 리디렉션해야 합니다.
    // **따라서 클라이언트 측에서 인증 시뮬레이션 코드는 삭제합니다.**
    
    // 이 함수가 DOMContentLoaded에서 호출되는 것만 남겨두고,
    // 실제 폼 제출을 막지 않도록 내부 로직은 제거합니다.
    
    // 이 함수가 호출되더라도, 폼의 기본 동작(서버로 POST 요청)이 실행되어야 합니다.
    // 만약 AJAX 로그인을 원한다면, 이 함수를 수정하여 `event.preventDefault();`를 사용해야 합니다.
    
    // 현재는 사용자님의 기존 코드 유지를 위해 이 함수는 그대로 두되, 
    // 로그인 페이지의 폼에 연결된 이벤트 리스너를 제거하고 Flask의 POST 요청을 사용해야 합니다.
}

// 페이지 로드 시 실행
document.addEventListener('DOMContentLoaded', () => {
    // [제거] 순수 JS로 updateAuthLink()를 호출하는 부분 제거
    // updateAuthLink(); 
    
    // 이 로직은 Flask 템플릿에서 직접 데이터를 받아 호출되어야 합니다.
    // 예시: <script> updateAuthLink(true, '책먹는 여우'); </script>

    // [제거] 로그인 폼 이벤트 리스너 제거 (Flask의 서버 측 폼 제출을 사용하도록 권장)
    // const loginForm = document.getElementById('login-form');
    // if (loginForm) {
    //     loginForm.addEventListener('submit', handleLogin);
    // }
});