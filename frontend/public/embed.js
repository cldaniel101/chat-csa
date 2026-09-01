(function () {
  var script = document.currentScript;

  if (!script || script.dataset.csaChatMounted === "true") {
    return;
  }

  script.dataset.csaChatMounted = "true";

  var scriptUrl = new URL(script.src, window.location.href);
  var chatUrl = new URL(script.dataset.chatUrl || scriptUrl.origin, window.location.href);
  var iframeUrl = new URL(chatUrl.href);
  iframeUrl.searchParams.set("embed", "1");

  if (script.dataset.consumerUrl) {
    iframeUrl.searchParams.set("consumerUrl", script.dataset.consumerUrl);
  }

  var position = script.dataset.position || "right";
  var bottom = script.dataset.bottom || "16px";
  var side = script.dataset.side || "16px";
  var zIndex = script.dataset.zIndex || "2147483000";

  var iframe = document.createElement("iframe");
  iframe.id = script.dataset.iframeId || "chat-csa-widget";
  iframe.title = script.dataset.title || "Assistente CSA";
  iframe.src = iframeUrl.toString();
  iframe.allow = "clipboard-write";
  iframe.setAttribute("aria-label", iframe.title);

  iframe.style.position = "fixed";
  iframe.style.bottom = bottom;
  iframe.style[position === "left" ? "left" : "right"] = side;
  iframe.style.width = "96px";
  iframe.style.height = "96px";
  iframe.style.border = "0";
  iframe.style.background = "transparent";
  iframe.style.colorScheme = "normal";
  iframe.style.zIndex = zIndex;
  iframe.style.overflow = "hidden";

  function resize(open) {
    var margin = 16;
    var closedWidth = 96;
    var closedHeight = 96;
    var openWidth = Math.min(432, Math.max(closedWidth, window.innerWidth - margin));
    var openHeight = Math.min(720, Math.max(closedHeight, window.innerHeight - margin));

    iframe.style.width = (open ? openWidth : closedWidth) + "px";
    iframe.style.height = (open ? openHeight : closedHeight) + "px";
  }

  window.addEventListener("message", function (event) {
    if (event.source !== iframe.contentWindow) {
      return;
    }

    var data = event.data || {};
    if (data.source !== "chat-csa" || data.type !== "csa-chat:state") {
      return;
    }

    resize(Boolean(data.open));
  });

  window.addEventListener("resize", function () {
    resize(iframe.style.width !== "96px");
  });

  resize(false);
  document.body.appendChild(iframe);
})();
