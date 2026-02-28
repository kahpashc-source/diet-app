<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>맘스락 식단 관리</title>
    <style>
        :root {
            --main-color: #6d4c41; /* 차분한 우드톤 */
            --bg-color: #f9f7f2;
            --accent-color: #e67e22;
        }
        body { font-family: 'Pretendard', sans-serif; background-color: var(--bg-color); margin: 0; padding: 20px; }
        
        /* 상단 헤더 섹션 */
        .header-container {
            display: flex;
            background: white;
            border-radius: 15px;
            padding: 30px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.05);
            margin-bottom: 30px;
            align-items: center;
        }
        .header-visual { flex: 1; display: flex; align-items: center; gap: 20px; }
        .header-visual img { width: 120px; height: 120px; border-radius: 50%; object-fit: cover; border: 3px solid var(--main-color); }
        
        .gongyang-text {
            flex: 2;
            font-style: italic;
            color: #555;
            line-height: 1.8;
            border-left: 4px solid var(--main-color);
            padding-left: 20px;
            font-size: 1.05rem;
        }

        /* 달력 섹션 (주말 제외) */
        .calendar-title { font-size: 1.5rem; font-weight: bold; margin-bottom: 15px; color: var(--main-color); }
        .calendar-grid {
            display: grid;
            grid-template-columns: repeat(5, 1fr); /* 5열 구성 (월-금) */
            gap: 10px;
            background: #eee;
            padding: 10px;
            border-radius: 10px;
        }
        .day-header {
            background: var(--main-color);
            color: white;
            padding: 10px;
            text-align: center;
            font-weight: bold;
            border-radius: 5px;
        }
        .day-cell {
            background: white;
            min-height: 120px;
            padding: 10px;
            border-radius: 5px;
            border: 1px solid #ddd;
            transition: transform 0.2s;
        }
        .day-cell:hover { transform: translateY(-3px); box-shadow: 0 5px 10px rgba(0,0,0,0.1); }
        .date-num { font-weight: bold; margin-bottom: 8px; display: block; }
        .input-area { width: 100%; border: none; border-bottom: 1px dashed #ccc; outline: none; font-size: 0.9rem; }
        
        .today { border: 2px solid var(--accent-color); background-color: #fff9f0; }
    </style>
</head>
<body>

    <div class="header-container">
        <div class="header-visual">
            <img src="https://images.unsplash.com/photo-1547592166-23ac45744acd?q=80&w=200&auto=format&fit=crop" alt="도시락">
            <div>
                <h2 style="margin:0; color:var(--main-color);">맘스락(MOM'S RAK)</h2>
                <p style="margin:5px 0 0; font-size:0.9rem; color:#888;">정성을 담은 공양 식단</p>
            </div>
        </div>
        <div class="gongyang-text">
            이 음식이 어디에서 왔는가<br>
            내 덕행으로는 받기가 부끄럽네<br>
            마음의 온갖 탐욕을 떠나...
        </div>
    </div>

    <div class="calendar-title">2026년 02월 입력 달력 (평일 전용)</div>
    <div class="calendar-grid">
        <div class="day-header">월 (MON)</div>
        <div class="day-header">화 (TUE)</div>
        <div class="day-header">수 (WED)</div>
        <div class="day-header">목 (THU)</div>
        <div class="day-header">금 (FRI)</div>

        <div class="day-cell"><span class="date-num">23</span><input class="input-area" placeholder="식단 입력..."></div>
        <div class="day-cell"><span class="date-num">24</span><input class="input-area" placeholder="식단 입력..."></div>
        <div class="day-cell"><span class="date-num">25</span><input class="input-area" placeholder="식단 입력..."></div>
        <div class="day-cell"><span class="date-num">26</span><input class="input-area" placeholder="식단 입력..."></div>
        <div class="day-cell"><span class="date-num">27</span><input class="input-area" placeholder="식단 입력..."></div>
        
        <div class="day-cell today"><span class="date-num">02 (월)</span><input class="input-area" placeholder="신규 주간 입력..."></div>
        <div class="day-cell"><span class="date-num">03</span></div>
        <div class="day-cell"><span class="date-num">04</span></div>
        <div class="day-cell"><span class="date-num">05</span></div>
        <div class="day-cell"><span class="date-num">06</span></div>
    </div>

</body>
</html>
