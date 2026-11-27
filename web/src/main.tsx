import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
// Self-hosted dot-matrix face for the printed lines (OFL-1.1). Nothing is fetched from outside.
import "@fontsource/doto/latin-900.css";
import "./styles/paper.css";
import "./styles/stamps.css";
import "./styles/print.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

