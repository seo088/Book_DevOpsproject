/* static/script.js - 통합 스크립트 */

// ============================================================
// 1. [기능 정의] 북마크 & 읽은 책 처리 (AJAX 로직 - 통합 함수)
// ============================================================
async function handleBookAction(btn, actionType) {
    const logoutLink = document.querySelector('a[href="/logout"]');
    if (!logoutLink && typeof IS_LOGGED_IN !== 'undefined' && !IS_LOGGED_IN) {
        if(confirm("로그인이 필요한 서비스입니다.\n로그인 페이지로 이동하시겠습니까?")) {
            location.href = "/login";
        }
        return;
    }

    const isbn = btn.dataset.isbn;
    const isActive = btn.classList.contains('active');
    let url;

    if (actionType === 'bookmark') {
        url = isActive ? `/bookmark/delete/${isbn}` : `/bookmark/add/${isbn}`;
    } else { // read
        url = `/mark-read/${isbn}`;
    }

    try {
        const res = await fetch(url, { method: 'POST', headers: {'Content-Type': 'application/json'} });
        const data = await res.json();
        
        if (data.success) {
            if (actionType === 'bookmark') {
                btn.classList.toggle('active'); 
            } else {
                if (data.action === 'added') {
                    btn.classList.add('active');
                    const parent = btn.closest('.card-action-row') || btn.closest('.book-detail-actions');
                    if (parent) {
                        const siblingBm = parent.querySelector('.btn-bookmark') || document.getElementById('add-bookmark-btn');
                        if(siblingBm) siblingBm.classList.remove('active');
                    }
                } else {
                    btn.classList.remove('active');
                }
            }
        } else {
            alert(data.message);
        }
    } catch (err) {
        console.error(err);
        alert("서버 통신 오류");
    }
}

// ============================================================
// 2. [기능 정의] 리스트 아이템 삭제 및 이동
// ============================================================

function deleteReadBook(event, bookId) {
    if(event) event.preventDefault();
    if (!confirm('정말 삭제하시겠습니까?')) return;
    
    fetch(`/read-book/delete/${bookId}`, { method: 'POST' })
    .then(r => r.json()).then(d => {
        alert(d.message);
        if (d.success) {
            const item = event.target.closest('.read-book-item');
            if (item) item.remove();
            const cnt = document.getElementById('total-read-count');
            if(cnt) cnt.innerText = Math.max(0, (parseInt(cnt.innerText)||0)-1);
            if(!document.querySelector('.read-book-item')) window.location.reload();
        }
    });
}

function deleteEssay(event, essayId) {
    if(event) event.preventDefault();
    if (!confirm('정말 삭제하시겠습니까?')) return;
    
    fetch(`/essay/delete/${essayId}`, { method: 'POST' })
    .then(r => r.json()).then(d => {
        alert(d.message);
        if (d.success) {
            const item = event.target.closest('.essay-item');
            if (item) item.remove();
            const cnt = document.getElementById('total-essay-count');
            if(cnt) cnt.innerText = Math.max(0, (parseInt(cnt.innerText)||0)-1);
            if(!document.querySelector('.essay-item')) window.location.reload();
        }
    });
}

function deleteBookmark(event, bookId) {
    if(event) event.preventDefault();
    if (!confirm('정말 삭제하시겠습니까?')) return;
    
    fetch(`/bookmark/delete/${bookId}`, { method: 'POST' })
    .then(r => r.json()).then(d => {
        alert(d.message);
        if (d.success) {
            const item = event.target.closest('.read-book-item') || event.target.closest('.book-bookmark');
            if(item) item.remove();
            const cnt = document.getElementById('bookmark-total-count');
            if(cnt) {
                let num = parseInt(cnt.innerText.replace(/[^0-9]/g, '')) || 0;
                cnt.innerText = `총 ${Math.max(0, num-1)}권`;
            }
            const listSection = document.querySelector('.read-books-list-section');
            if (listSection && listSection.children.length === 0) window.location.reload();
        }
    });
}

function moveToRead(event, bookId) {
    if(event) event.preventDefault();
    if (!confirm('이 책을 [읽은 책] 목록으로 이동하시겠습니까?\n(북마크 목록에서는 사라집니다.)')) return;
    
    fetch(`/mark-read/${bookId}`, { method: 'POST' })
    .then(r => r.json()).then(d => {
        alert(d.message);
        if (d.success) window.location.reload();
    });
}
const moveToReadFromMypage = moveToRead;


// ============================================================
// 3. [기능 정의] 리뷰 팝업 로직 (데이터 로드 포함)
// ============================================================

function updateModalStars(rating) {
    const stars = document.querySelectorAll("#reviewModal .star-icon");
    stars.forEach(star => {
        const starValue = parseInt(star.getAttribute('data-rating'));
        star.className = 'far fa-star star-icon';
        star.style.color = '#ccc';

        if (rating >= starValue) {
            star.className = 'fas fa-star star-icon filled';
            star.style.color = '#FFD700';
        } else if (rating >= starValue - 0.5) {
            star.className = 'fas fa-star-half-alt star-icon filled';
            star.style.color = '#FFD700';
        }
    });
}

async function openReviewModal(bookId, bookName, event) {
    if (event) event.preventDefault();

    const modal = document.getElementById("reviewModal");
    const ratingInput = document.getElementById("ratingValue");
    const contentTextarea = document.querySelector('#review-form textarea[name="content"]');
    const submitBtn = document.querySelector('#review-form button[type="submit"]');

    if (!modal) return;
    
    document.getElementById('modalBookId').value = bookId;
    document.getElementById('modal-book-name').textContent = bookName;
    
    if(ratingInput) ratingInput.value = 0;
    if(contentTextarea) contentTextarea.value = "";
    updateModalStars(0);
    if(submitBtn) submitBtn.textContent = "리뷰 등록"; 

    modal.style.display = "block";

    try {
        const response = await fetch(`/get_review/${bookId}`);
        const data = await response.json();

        if (data.success) {
            if (ratingInput) ratingInput.value = data.rating;
            if (contentTextarea) contentTextarea.value = data.content;
            updateModalStars(data.rating); 
            if(submitBtn) submitBtn.textContent = "리뷰 수정"; 
        }
    } catch (err) {
        console.error("리뷰 데이터 로드 실패:", err);
    }
}

function setupReviewModalFeatures() {
    const modal = document.getElementById("reviewModal");
    const closeBtn = document.getElementById("closeReviewModal");
    const stars = document.querySelectorAll("#reviewModal .star-icon");
    const ratingInput = document.getElementById("ratingValue");
    const starContainer = document.querySelector(".stars-input");
    const reviewForm = document.getElementById('review-form');

    if (!modal) return;

    if (closeBtn) closeBtn.onclick = () => modal.style.display = "none";
    window.onclick = (e) => { if (e.target === modal) modal.style.display = "none"; };

    stars.forEach(star => {
        star.addEventListener('mousemove', function(e) {
            const width = this.offsetWidth;
            const clickX = e.offsetX;
            let rating = parseInt(this.getAttribute('data-rating'));
            if (clickX < width / 2) rating -= 0.5;
            updateModalStars(rating); 
        });

        star.addEventListener('click', function(e) {
            const width = this.offsetWidth;
            const clickX = e.offsetX;
            let rating = parseInt(this.getAttribute('data-rating'));
            if (clickX < width / 2) rating -= 0.5;
            ratingInput.value = rating; 
            updateModalStars(rating); 
        });
    });

    if (starContainer) {
        starContainer.addEventListener('mouseleave', function() {
            const currentRating = parseFloat(ratingInput.value) || 0;
            updateModalStars(currentRating);
        });
    }

    if (reviewForm) {
        reviewForm.onsubmit = async function(e) {
            e.preventDefault();
            const ratingVal = ratingInput.value;
            if (!ratingVal || ratingVal == 0) {
                alert("별점을 매겨주세요.");
                return;
            }
            const bookId = document.getElementById('modalBookId').value;
            const formData = new FormData(this);
            try {
                const response = await fetch(`/add_review/${bookId}`, { method: 'POST', body: formData });
                const result = await response.json();
                if (result.success) {
                    alert(result.message);
                    modal.style.display = "none";
                    window.location.href = '/my-reviews'; 
                } else {
                    alert("오류: " + result.message);
                }
            } catch (err) { console.error(err); alert("통신 오류"); }
        };
    }
}

// ============================================================
// 4. [기능 정의] 사용자 검색 기능
// ============================================================
function bindUserSearch() {
    const searchForm = document.getElementById('user-search-form');
    
    if (searchForm) {
        searchForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            const input = document.getElementById('user-search-input');
            const nickname = input.value.trim();

            if (!nickname) {
                alert("닉네임을 입력해주세요.");
                return;
            }

            try {
                const response = await fetch('/search/user', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ nickname: nickname })
                });
                const data = await response.json();

                if (data.success) {
                    window.location.href = `/profile/${data.user_id}`;
                } else {
                    alert(data.message);
                }
            } catch (err) {
                console.error(err);
                alert("검색 중 오류가 발생했습니다.");
            }
        });
    }
}


// ============================================================
// 5. [실행] 초기화 및 이벤트 바인딩
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
    
    // 1. 햄버거 메뉴
    const openBtn = document.getElementById('open-menu-btn');
    const closeBtn = document.getElementById('close-menu-btn');
    const sideMenu = document.getElementById('side-menu');
    if (openBtn && sideMenu) openBtn.addEventListener('click', () => sideMenu.classList.add('open'));
    if (closeBtn && sideMenu) closeBtn.addEventListener('click', () => sideMenu.classList.remove('open'));

    // 2. 장르 필터
    const genreBtn = document.getElementById('genre-filter-btn');
    const genreOptions = document.getElementById('genre-filter-options');
    const genreArrow = document.getElementById('genre-arrow'); // 화살표 요소 추가

    if (genreBtn && genreOptions) {
        // 기존 리스너 제거 방지를 위해 cloneNode를 쓰거나, 그냥 아래 로직만 남깁니다.
        // 가장 확실한 건 script.js의 이 부분을 이걸로 '교체'하는 것입니다.
        genreBtn.addEventListener('click', (e) => {
            e.preventDefault(); // 기본 동작 방지
            
            const isHidden = genreOptions.style.display === 'none' || genreOptions.style.display === '';
            
            if (isHidden) {
                genreOptions.style.display = 'block';
                if (genreArrow) genreArrow.style.transform = 'rotate(180deg)';
            } else {
                genreOptions.style.display = 'none';
                if (genreArrow) genreArrow.style.transform = 'rotate(0deg)';
            }
        });
    }

    // 3. 탭 전환
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabPanes = document.querySelectorAll('.tab-pane');
    if (tabBtns.length > 0) {
        tabBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                tabBtns.forEach(b => b.classList.remove('active'));
                tabPanes.forEach(p => p.classList.remove('active'));
                btn.classList.add('active');
                const targetId = btn.getAttribute('data-tab');
                const targetPane = document.getElementById(targetId);
                if (targetPane) targetPane.classList.add('active');
            });
        });
    }

    // 4. 버튼 이벤트 연결 (리스트형)
    document.querySelectorAll('.btn-bookmark').forEach(btn => {
        btn.addEventListener('click', (e) => { e.preventDefault(); handleBookAction(btn, 'bookmark'); });
    });
    document.querySelectorAll('.btn-read').forEach(btn => {
        btn.addEventListener('click', (e) => { e.preventDefault(); handleBookAction(btn, 'read'); });
    });

    // 5. 버튼 이벤트 연결 (상세형)
    const detailBmBtn = document.getElementById('add-bookmark-btn');
    const detailReadBtn = document.getElementById('mark-read-btn');
    if (detailBmBtn) detailBmBtn.addEventListener('click', () => handleBookAction(detailBmBtn, 'bookmark'));
    if (detailReadBtn) detailReadBtn.addEventListener('click', () => handleBookAction(detailReadBtn, 'read'));

    // 6. 리뷰 모달 초기화
    setupReviewModalFeatures();

    // 7. 플래시 메시지 자동 숨김
    const flashMsg = document.querySelector('.flash-messages');
    if (flashMsg) setTimeout(() => flashMsg.style.display = 'none', 3000);

    // 8. ★ [핵심] 사용자 검색 연결 호출
    bindUserSearch();
});

/* [추가] 팔로우 토글 기능 */
async function toggleFollow(targetId) {
    const btn = document.getElementById('follow-btn');
    const countSpan = document.getElementById('follower-count');

    try {
        const response = await fetch(`/toggle_follow/${targetId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();

        if (data.success) {
            // 팔로워 수 즉시 갱신
            if (countSpan) countSpan.innerText = data.new_count;

            // 버튼 스타일 및 텍스트 변경
            if (data.action === 'followed') {
                // 팔로우 상태로 변경 (회색 버튼)
                btn.className = 'action-btn secondary-btn small-btn';
                btn.innerHTML = '<i class="fas fa-check"></i> 팔로잉';
            } else {
                // 언팔로우 상태로 변경 (주황색 버튼)
                btn.className = 'action-btn primary-btn small-btn';
                btn.innerHTML = '<i class="fas fa-user-plus"></i> 팔로우';
            }
        } else {
            if (data.need_login) {
                if(confirm("로그인이 필요합니다. 로그인 페이지로 이동할까요?")) {
                    location.href = "/login";
                }
            } else {
                alert(data.message);
            }
        }
    } catch (err) {
        console.error(err);
        alert("통신 오류가 발생했습니다.");
    }
}

// --- [추가] 팔로우/팔로워 목록 모달 열기 ---
async function openFollowListModal(targetUserId, type) {
    const modal = document.getElementById('followListModal');
    const title = document.getElementById('followModalTitle');
    const listContainer = document.getElementById('followListContent');
    
    if (!modal) return;

    // 1. 제목 설정
    title.innerText = (type === 'following') ? "팔로잉 목록" : "팔로워 목록";
    listContainer.innerHTML = '<p style="text-align:center; padding:20px;">로딩 중...</p>';
    
    // 2. 모달 표시
    modal.style.display = 'block';

    // 3. 데이터 가져오기
    try {
        const response = await fetch(`/api/follow_list/${targetUserId}/${type}`);
        const data = await response.json();

        listContainer.innerHTML = ''; // 로딩 문구 제거

        if (data.success && data.list.length > 0) {
            data.list.forEach(user => {
                const item = document.createElement('div');
                item.className = 'follow-user-item';
                item.onclick = () => { window.location.href = `/profile/${user.user_id}`; }; // 클릭 시 이동

                // 프로필 이미지 처리
                let imgHtml = '';
                if (user.profile_image) {
                    imgHtml = `<div class="follow-user-img" style="background-image: url('/static/uploads/${user.profile_image}')"></div>`;
                } else {
                    imgHtml = `<div class="follow-user-img"><i class="fas fa-user"></i></div>`;
                }

                item.innerHTML = `
                    ${imgHtml}
                    <div class="follow-user-info">
                        <strong>${user.nickname}</strong>
                    </div>
                `;
                listContainer.appendChild(item);
            });
        } else {
            listContainer.innerHTML = '<p style="text-align:center; padding:20px; color:#999;">목록이 비어있습니다.</p>';
        }

    } catch (err) {
        console.error(err);
        listContainer.innerHTML = '<p style="text-align:center; padding:20px; color:red;">불러오기 실패</p>';
    }

    // 4. 닫기 버튼 이벤트
    const closeBtn = document.getElementById('closeFollowModal');
    if(closeBtn) closeBtn.onclick = () => modal.style.display = 'none';
    
    // 모달 바깥 클릭 시 닫기
    window.onclick = (event) => {
        if (event.target == modal) {
            modal.style.display = 'none';
        }
    };
}

// 전역 함수 노출
window.deleteReadBook = deleteReadBook;
window.deleteEssay = deleteEssay;
window.deleteBookmark = deleteBookmark;
window.moveToRead = moveToRead;
window.moveToReadFromMypage = moveToReadFromMypage;
window.openReviewModal = openReviewModal;