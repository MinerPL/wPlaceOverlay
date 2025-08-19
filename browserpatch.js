(async () => {
    // === Load config for tile spoofing ===
    const tilesconfig = await (
        await fetch("http://localhost:8000/config.json", { cache: "reload" })
    ).json();
    console.log("Loaded config:", tilesconfig);

    const origFetch = window.fetch;

    // Control flags
    let spoofEnabled = false;
    let overrideNext = false;

    // === UI Buttons ===
    // Spoofer button
    const spooferBtn = document.createElement("button");
    spooferBtn.textContent = "Spoofer OFF";
    Object.assign(spooferBtn.style, {
        position: "fixed",
        bottom: "20px",
        right: "20px",
        zIndex: "9999",
        padding: "10px 16px",
        background: "red",
        color: "white",
        border: "none",
        borderRadius: "8px",
        cursor: "pointer",
        fontSize: "14px",
        marginLeft: "10px",
    });
    document.body.appendChild(spooferBtn);

    spooferBtn.addEventListener("click", () => {
        spoofEnabled = !spoofEnabled;
        spooferBtn.style.background = spoofEnabled ? "green" : "red";
        spooferBtn.textContent = spoofEnabled ? "Spoofer ON" : "Spoofer OFF";
    });

    // Override paint button
    const paintBtn = document.createElement("button");
    paintBtn.textContent = "Override Paint";
    Object.assign(paintBtn.style, {
        position: "fixed",
        bottom: "60px",
        right: "20px",
        zIndex: "9999",
        padding: "10px 16px",
        background: "red",
        color: "white",
        border: "none",
        borderRadius: "8px",
        cursor: "pointer",
        fontSize: "14px",
    });
    document.body.appendChild(paintBtn);

    paintBtn.addEventListener("click", () => {
        const ans = confirm("Do you want to override the next paint request?");
        overrideNext = ans;
        if (ans) {
            paintBtn.style.background = "green";
            paintBtn.textContent = "Override Active";
        } else {
            paintBtn.style.background = "red";
            paintBtn.textContent = "Override Paint";
        }
    });

    // === Proxy fetch ===
    window.fetch = new Proxy(origFetch, {
        apply: async (target, thisArg, argList) => {
            if (!argList[0]) throw new Error("No URL provided to fetch");

            const urlString =
                typeof argList[0] === "object" ? argList[0].url : argList[0];
            let url;
            try {
                url = new URL(urlString, location.href);
            } catch {
                throw new Error("Invalid URL provided to fetch: " + urlString);
            }

            // --- TILE SPOOFER ---
            if (spoofEnabled && url.pathname !== "/config.json") {
                let match = false;
                for (const [x, y] of tilesconfig) {
                    if (url.pathname === `/files/s0/tiles/${x}/${y}.png`) {
                        match = true;
                        break;
                    }
                }

                if (url.hostname === "backend.wplace.live" && match) {
                    url.host = "localhost:8000";
                    url.protocol = "http:";
                    console.log("🔄 Spoofed URL →", url.toString());

                    if (typeof argList[0] === "object") {
                        argList[0] = new Request(url, argList[0]);
                    } else {
                        argList[0] = url.toString();
                    }
                }
            }

            // --- PAINT OVERRIDE ---
            if (
                overrideNext &&
                url.pathname.includes("/pixel/") &&
                argList[1]?.method === "POST"
            ) {
                try {
                    const data = JSON.parse(argList[1].body);

                    const coords = url.pathname.split("/").slice(-2);

                    const res = await origFetch("http://127.0.0.1:8000/colors");
                    const extra = await res.json();

                    const pixelsPlacement = extra[coords[0]][coords[1]];

                    const pixels = parseInt(prompt(
                        `Override enabled.\nHow many pixels do you have? (server says: ${pixelsPlacement.colors.length})`
                    ));

                    data.coords = pixelsPlacement.coords.slice(0, pixels * 2)
                    data.colors = pixelsPlacement.colors.slice(0, pixels);

                    argList[1].body = JSON.stringify(data);

                    console.log("🎨 Payload overridden:", data);

                    // reset after one use
                    overrideNext = false;
                    paintBtn.style.background = "red";
                    paintBtn.textContent = "Override Paint";
                } catch (err) {
                    console.error("Paint override failed:", err);
                }
            }

            return target.apply(thisArg, argList);
        },
    });
})();
