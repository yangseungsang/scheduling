/**
 * 바코드 스캔 시뮬레이터
 *
 * 사용법: 브라우저 콘솔(F12)에서 이 코드를 붙여넣고 실행
 * 주의: INPUT/TEXTAREA에 포커스가 없어야 동작함 (빈 영역 클릭 후 실행)
 */

function simulateBarcode(code) {
  for (const ch of code) {
    document.dispatchEvent(new KeyboardEvent('keydown', { key: ch }));
  }
  document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
  console.log('[barcode-test] 전송:', code);
}

// ── 테스트 예시 ────────────────────────────────────────────────────────��─

// 목록 페이지에서: 해당 식별자 상세 페이지로 이동 + 자동시작
// simulateBarcode('OPEN-TC-001');

// 상세 페이지에서: 시험 일시정지
// simulateBarcode('TERMINATE');

// 상세 페이지에서: 다른 식별자로 이동
// simulateBarcode('OPEN-TC-002');
