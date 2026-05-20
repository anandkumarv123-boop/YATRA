import { useEffect } from "react";

function App() {
  useEffect(() => {
    window.location.replace("/app.html");
  }, []);
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh", background: "#050709", color: "#F0F4FF", fontFamily: "sans-serif" }}>
      <div data-testid="redirect-loading">Loading Yatra Sathi…</div>
    </div>
  );
}

export default App;
