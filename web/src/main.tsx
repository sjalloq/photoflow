import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "react-photo-album/rows.css";
import "yet-another-react-lightbox/styles.css";
import "./app.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
