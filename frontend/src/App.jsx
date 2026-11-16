import React, { useEffect, useState } from "react";
import RfqList from "./components/RfqList.jsx";
import CreateRfq from "./components/CreateRfq.jsx";
import RfqDetail from "./components/RfqDetail.jsx";

function useHash() {
  const [hash, setHash] = useState(window.location.hash || "#/");
  useEffect(() => {
    const on = () => setHash(window.location.hash || "#/");
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return hash;
}

export default function App() {
  const hash = useHash();
  const detail = hash.match(/^#\/rfq\/(\d+)/);

  let page;
  if (hash === "#/new") page = <CreateRfq />;
  else if (detail) page = <RfqDetail id={Number(detail[1])} key={detail[1]} />;
  else page = <RfqList />;

  return (
    <>
      <header className="topbar">
        <a href="#/" className="brand">British Auction · RFQ</a>
        <nav>
          <a href="#/">Auctions</a>
          <a href="#/new" className="btn primary">+ New RFQ</a>
        </nav>
      </header>
      <main className="container">{page}</main>
    </>
  );
}
