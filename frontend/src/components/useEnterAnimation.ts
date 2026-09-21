import { useEffect, useState } from "react";

/** `false` сразу при монтировании, переключается в `true` через кадр — триггер CSS-transition
 * для «наполняющихся» баров/колец/графиков при заходе на страницу. Переход по роуту
 * размонтирует прошлую страницу (React remount), поэтому срабатывает и на переходах между
 * вкладками сайта, и при первом открытии. */
export function useEnterAnimation(): boolean {
  const [entered, setEntered] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setEntered(true));
    return () => cancelAnimationFrame(id);
  }, []);
  return entered;
}
