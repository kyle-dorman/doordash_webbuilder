// Reflect the menu section at the top of the viewport in the section index.
const links = Array.from(document.querySelectorAll(".section-links a"));
const sections = links.map(link => document.getElementById(link.hash.slice(1)));
let activeLink;
let pending = false;

function updateSection() {
  let current;
  for (let i = 0; i < sections.length; i += 1) {
    if (sections[i].getBoundingClientRect().top > 40) break;
    current = links[i];
  }
  current ??= links[0];
  // The last few headings may be too close to the footer to reach the top.
  if (window.scrollY > 0 && window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 1) {
    const target = links.find(link => link.hash === window.location.hash);
    const headingTop = target && document.getElementById(target.hash.slice(1)).getBoundingClientRect().top;
    current = headingTop >= 0 && headingTop < window.innerHeight ? target : links.at(-1);
  }
  if (current !== activeLink) {
    activeLink?.removeAttribute("aria-current");
    current?.setAttribute("aria-current", "location");
    activeLink = current;
  }
  pending = false;
}

function scheduleUpdate() {
  if (!pending) {
    pending = true;
    requestAnimationFrame(updateSection);
  }
}

updateSection();
window.addEventListener("scroll", scheduleUpdate, {passive: true});
window.addEventListener("resize", scheduleUpdate);
window.addEventListener("hashchange", scheduleUpdate);
