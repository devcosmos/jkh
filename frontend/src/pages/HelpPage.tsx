import { Link } from "react-router-dom";
import { getRole } from "../api/client";
import { Badge } from "../components/Badge";

interface SectionInfo {
  title: string;
  to: string;
  text: string;
  details: string[];
  adminOnly?: boolean;
}

const SECTIONS: SectionInfo[] = [
  {
    title: "Обзор",
    to: "/dashboard",
    text: "Общая картина по всей системе одним взглядом, без необходимости открывать другие разделы.",
    details: [
      "Сколько сейчас открытых рисков всего, сколько из них критичны и сколько отмечено как аномальные",
      "Разбивка рисков по обоим направлениям отдельно, с временем последнего расчёта по каждому",
      "Заявки по статусам — сколько ещё черновиков, сколько в работе, сколько выполнено",
      "Топ объектов с наибольшим числом открытых рисков",
      "Точность (ROC-AUC) работающих сейчас моделей по каждому направлению",
    ],
  },
  {
    title: "Риски",
    to: "/risks",
    text: "Главный рабочий экран диспетчера — здесь принимаются решения.",
    details: [
      "Таблица случаев с повышенным риском отказа, по умолчанию отсортирована по вероятности отказа (по клику на заголовок колонки можно сортировать и по дате открытия)",
      "Фильтры по статусу и по направлению (насос/вентилятор или дым/газ)",
      "Переключатель «Список» / «Схема объектов» — второй режим показывает иерархию объектов с цветовой индикацией риска вместо таблицы",
      "Клик по строке открывает справа карточку с объяснением прогноза, историей неисправностей и кнопками решения — подробнее в разделе «Как принять решение по риску» ниже",
    ],
  },
  {
    title: "Журнал",
    to: "/journal",
    text: "Полная история всех расчётов модели, не только тех, что превысили порог срабатывания.",
    details: [
      "Каждая строка — один расчёт вероятности по одному датчику в конкретный момент времени",
      "Фильтр по направлению; строки старше суток подсвечены как устаревшие",
      "Клик по строке разворачивает то же резюме ИИ и объяснение прогноза, что и в карточке риска — удобно для разбора конкретного случая или проверки, почему модель не сработала",
    ],
  },
  {
    title: "Заявки",
    to: "/requests",
    text: "Заявки на обслуживание оборудования — то, что должно привести к реальному визиту специалиста.",
    details: [
      "Заявка создаётся только вручную — когда диспетчер направляет риск на проверку из карточки риска",
      "У каждой заявки видно объект, канал и ссылку на риск-кейс, по которому она создана",
      "Клик по строке разворачивает резюме ИИ, аномалию и решение диспетчера, полное обоснование заявки и ход выполнения: когда создана, утверждена и кем",
      "Кнопки действий двигают заявку по цепочке статусов — подробнее в разделе «Как отследить заявку» ниже",
    ],
  },
  {
    title: "Модели",
    to: "/models",
    text: "Что именно сейчас принимает решения за системой.",
    details: [
      "Активная версия модели по каждому направлению, дата обучения",
      "Точность модели (ROC-AUC) и достигнута ли плановая цель по качеству",
      "Рабочий порог вероятности, при превышении которого случай попадает в «Риски», и обоснование, почему выбран именно он",
    ],
  },
  {
    title: "Объекты и каналы",
    to: "/registry",
    text: "Справочник оборудования — какие датчики к какому объекту относятся.",
    details: [
      "Поиск по названию канала или расположению",
      "Фильтр по типу датчика",
      "Фильтр по конкретному объекту — можно выбрать из списка или кликнуть по названию объекта прямо в таблице, чтобы увидеть только его датчики",
    ],
  },
  {
    title: "Журнал аудита",
    to: "/audit-log",
    text: "Полная история изменений в системе — для прослеживаемости.",
    details: [
      "Кто и когда принял решение по риску, изменил статус заявки или выдал/отозвал доступ пользователю к объекту",
      "Фильтр по типу записи",
    ],
    adminOnly: true,
  },
  {
    title: "Пользователи",
    to: "/users",
    text: "Управление учётными записями и доступом к объектам.",
    details: [
      "Список пользователей с ролями (администратор, диспетчер, аналитик)",
      "Создание новой учётной записи",
      "Назначение и отзыв доступа к конкретным объектам — если пользователю ничего не назначено явно, ограничение не действует",
    ],
    adminOnly: true,
  },
];

const STEPS = [
  {
    title: "Откройте «Риски»",
    text: "Список по умолчанию отсортирован по вероятности отказа — сверху самые срочные случаи. При необходимости отфильтруйте по статусу или направлению.",
  },
  {
    title: "Откройте карточку",
    text: "Клик по строке — справа появится карточка с деталями конкретного случая.",
  },
  {
    title: "Изучите объяснение прогноза",
    text: "Блок «Почему сработал прогноз» показывает, какие именно показания датчика повлияли на решение модели сильнее всего, и в какую сторону — повышают они риск отказа или, наоборот, снижают его. Если рядом стоит отметка «Аномальное поведение» — это отдельная, независимая проверка, которая заметила необычное поведение датчика, даже если основная модель сама по себе не считает его крайне рискованным. Совпадение двух независимых сигналов — более сильный повод обратить внимание, и именно поэтому такому случаю сразу присваивается более высокий приоритет.",
  },
  {
    title: "Посмотрите историю неисправностей",
    text: "Если у датчика уже случались сбои раньше, они показаны внизу карточки — со своей прокруткой, чтобы длинная история не мешала основному решению.",
  },
  {
    title: "Примите решение",
    text: "«Направить на проверку» — переводит случай в работу и создаёт (или связывает уже существующую) заявку на обслуживание. «Наблюдать» — оставить на контроле, ничего не предпринимая пока. «Уточнить данные» — если показаниям не хватает доверия. «Отклонить предупреждение» — если это ложное срабатывание. К любому решению можно добавить комментарий.",
  },
  {
    title: "Перейдите к заявке",
    text: "После решения статус сразу обновится на карточке. Если появилась заявка — рядом появится кнопка «Смотреть заявку», которая откроет её в разделе «Заявки».",
  },
];

const REQUEST_STAGES = [
  { label: "Черновик", text: "заявка создана диспетчером, ещё не рассмотрена" },
  { label: "Утверждена", text: "подтверждена диспетчером или администратором" },
  { label: "В работе", text: "обслуживание выполняется" },
  { label: "Выполнена", text: "работа завершена" },
];

const FAQ = [
  {
    q: "Почему вероятность не 100%, если модель «уверена»?",
    a: "Модель никогда не даёт гарантию — только вероятность на основе истории похожих случаев. Чем выше вероятность и чем больше признаков ей соответствует, тем надёжнее сигнал, но полной определённости не бывает никогда.",
  },
  {
    q: "Что значит «Аномальное поведение»?",
    a: "Это отдельная, независимая от основной модели проверка. Она ищет необычные паттерны в поведении датчика, непохожие ни на один из ранее известных случаев поломки. Если она срабатывает одновременно с основным прогнозом — риску сразу присваивается более высокий приоритет.",
  },
  {
    q: "Почему нет карты с реальными координатами объектов?",
    a: "Точные координаты объектов не передаются и не появятся — это подтверждено владельцами данных. Вместо GPS-карты в разделе «Риски» показана иерархическая схема объектов с цветовой индикацией риска — по ней так же видно, где сосредоточены проблемы.",
  },
  {
    q: "Что если я закрою страницу, не приняв решение?",
    a: "Ничего не потеряется. Риск-кейс останется в разделе «Риски» со своим статусом, вернуться к нему можно в любой момент.",
  },
  {
    q: "Кто видит все объекты, а кто — только часть?",
    a: "Администратор видит всё без ограничений. Остальным пользователям объекты можно назначать точечно в разделе «Пользователи» — если пользователю ничего не назначено явно, ограничение не действует.",
  },
  {
    q: "Чем отличаются направления «Насос/вентилятор» и «Дым/газ»?",
    a: "Это два разных типа оборудования, которые оцениваются полностью независимо друг от друга: у каждого своя модель, свой порог срабатывания и своя точность. Фильтр «Направление» есть на всех экранах со списками.",
  },
  {
    q: "Заявка на обслуживание и риск-кейс — это одно и то же?",
    a: "Нет. Риск-кейс — это предупреждение модели («вот этот датчик может отказать»), которое живёт в разделе «Риски». Заявка на обслуживание — это уже запрос на реальную работу специалиста, который живёт в разделе «Заявки». Одно решение диспетчера связывает их между собой, но это две разные сущности со своим статусом и историей.",
  },
];

export function HelpPage() {
  const isAdmin = getRole() === "admin";
  const apiExample = [
    `curl "${window.location.origin}/api/risk-cases?limit=10&offset=0" \\`,
    '  -H "Authorization: Bearer <access_token>"',
  ].join("\n");

  return (
    <div className="mx-auto max-w-[100rem] px-6 py-8">
      <div className="mb-8">
        <h1 className="font-display text-2xl font-semibold text-slate-900">Справка</h1>
        <p className="mt-1 text-sm text-slate-500">Что это за сервис и как им пользоваться</p>
      </div>

      <section className="mb-8 rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="mb-3 font-display text-lg font-semibold text-slate-900">О сервисе</h2>
        <p className="text-sm leading-relaxed text-slate-700">
          Сервис заранее предупреждает о возможном отказе датчика — до того, как он реально
          выйдет из строя, — чтобы обслуживание можно было спланировать заранее, а не устранять
          поломку по факту. Система следит за двумя видами оборудования отдельно друг от друга:{" "}
          <b className="text-slate-900">насосами и вентиляторами</b> и{" "}
          <b className="text-slate-900">датчиками дыма и газа</b>. По каждому направлению
          работает своя модель, обученная на истории показаний именно этого типа датчиков, и её
          решения нигде не смешиваются с решениями по другому направлению.
        </p>
        <p className="mt-3 text-sm leading-relaxed text-slate-700">
          Весь путь выглядит так: датчик передаёт показания → модель на их основе считает
          вероятность отказа (раздел{" "}
          <Link to="/journal" className="font-medium text-sky-700 hover:underline">
            «Журнал»
          </Link>
          ) → если вероятность превысила рабочий порог, появляется предупреждение (раздел{" "}
          <Link to="/risks" className="font-medium text-sky-700 hover:underline">
            «Риски»
          </Link>
          ) → диспетчер принимает решение → если нужно обслуживание, оно оформляется как заявка
          (раздел{" "}
          <Link to="/requests" className="font-medium text-sky-700 hover:underline">
            «Заявки»
          </Link>
          ) и доводится до выполнения.
        </p>
      </section>

      <section className="mb-8">
        <h2 className="mb-4 font-display text-lg font-semibold text-slate-900">Из чего состоит панель</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {SECTIONS.map((s) => (
            <div key={s.title} className="rounded-2xl border border-slate-200 bg-white p-4">
              <div className="mb-1.5 flex items-center gap-2">
                {!s.adminOnly || isAdmin ? (
                  <Link to={s.to} className="font-display text-sm font-semibold text-sky-700 hover:underline">
                    {s.title} &gt;
                  </Link>
                ) : (
                  <span className="font-display text-sm font-semibold text-slate-900">{s.title}</span>
                )}
                {s.adminOnly && <Badge tone="neutral">Только администратор</Badge>}
              </div>
              <p className="mb-2 text-sm text-slate-600">{s.text}</p>
              <ul className="space-y-1 text-sm text-slate-500">
                {s.details.map((d) => (
                  <li key={d} className="flex gap-1.5">
                    <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-slate-300" />
                    <span>{d}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      <section className="mb-8 rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="mb-1 font-display text-lg font-semibold text-slate-900">Как принять решение по риску</h2>
        <p className="mb-4 text-sm text-slate-500">
          Пошагово, от открытия{" "}
          <Link to="/risks" className="font-medium text-sky-700 hover:underline">
            «Рисков»
          </Link>{" "}
          до перехода в связанную заявку
        </p>
        <ol className="space-y-4">
          {STEPS.map((s, i) => (
            <li key={s.title} className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-sky-50 text-sm font-semibold text-sky-700">
                {i + 1}
              </span>
              <div>
                <div className="text-sm font-semibold text-slate-900">{s.title}</div>
                <p className="mt-0.5 text-sm text-slate-600">{s.text}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="mb-8 rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="mb-1 font-display text-lg font-semibold text-slate-900">Как отследить заявку</h2>
        <p className="mb-4 text-sm text-slate-500">
          Заявка на обслуживание, созданная в{" "}
          <Link to="/requests" className="font-medium text-sky-700 hover:underline">
            «Заявках»
          </Link>
          , проходит по цепочке статусов
        </p>
        <ol className="mb-4 flex flex-wrap items-center gap-2 text-sm">
          {REQUEST_STAGES.map((stage, i) => (
            <li key={stage.label} className="flex items-center gap-2">
              <span className="rounded-full bg-slate-100 px-3 py-1 font-medium text-slate-700" title={stage.text}>
                {stage.label}
              </span>
              {i < REQUEST_STAGES.length - 1 && <span className="text-slate-300">→</span>}
            </li>
          ))}
        </ol>
        <p className="text-sm text-slate-600">
          Вместо «Утверждена» заявку можно отклонить (если решили, что обслуживание не нужно), а
          вместо «Выполнена» — отменить на любом этапе после утверждения. Открыв заявку кликом по
          строке, вы увидите полное обоснование (почему она была создана: какой канал, объект,
          направление, при какой вероятности отказа), резюме ИИ и сигнал аномалии по риску,
          решение диспетчера, ход выполнения и полную историю изменений (кто, когда и на какой
          статус перевёл заявку) — вместе со ссылкой обратно на риск-кейс, из которого заявка
          появилась.
        </p>
      </section>

      <section className="mb-8 rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="mb-4 font-display text-lg font-semibold text-slate-900">Термины</h2>
        <dl className="grid gap-4 sm:grid-cols-2">
          <div>
            <dt className="text-sm font-semibold text-slate-900">Риск-кейс</dt>
            <dd className="mt-0.5 text-sm text-slate-600">
              Предупреждение модели о повышенной вероятности отказа конкретного датчика. Живёт в
              разделе{" "}
              <Link to="/risks" className="font-medium text-sky-700 hover:underline">
                «Риски»
              </Link>
              , пока диспетчер не примет решение или пока не перестанут поступать новые
              предупреждения по этому датчику.
            </dd>
          </div>
          <div>
            <dt className="text-sm font-semibold text-slate-900">Заявка на обслуживание</dt>
            <dd className="mt-0.5 text-sm text-slate-600">
              Запрос на реальную работу специалиста, созданный по риск-кейсу. Живёт в разделе{" "}
              <Link to="/requests" className="font-medium text-sky-700 hover:underline">
                «Заявки»
              </Link>{" "}
              и имеет собственный статус, отдельный от статуса риск-кейса.
            </dd>
          </div>
          <div>
            <dt className="text-sm font-semibold text-slate-900">Направление (трек)</dt>
            <dd className="mt-0.5 text-sm text-slate-600">
              Одна из двух независимо оцениваемых групп оборудования: «Насос/вентилятор» или
              «Дым/газ». У каждой — своя модель, свой порог срабатывания и своя точность.
            </dd>
          </div>
          <div>
            <dt className="text-sm font-semibold text-slate-900">Вероятность отказа</dt>
            <dd className="mt-0.5 text-sm text-slate-600">
              Оценка модели от 0 до 100% на ближайшие сутки. Не гарантия, а мера уверенности на
              основе истории похожих случаев — подробнее в разделе «Частые вопросы» ниже.
            </dd>
          </div>
          <div>
            <dt className="text-sm font-semibold text-slate-900">Приоритет</dt>
            <dd className="mt-0.5 text-sm text-slate-600">
              Высокий или средний — определяется по вероятности отказа и по тому, отметила ли
              независимая проверка поведение датчика как аномальное.
            </dd>
          </div>
          <div>
            <dt className="text-sm font-semibold text-slate-900">Эпизод</dt>
            <dd className="mt-0.5 text-sm text-slate-600">
              Зафиксированный период, когда датчик действительно находился в неисправном
              состоянии. Показывается в карточке риска отдельно от прогноза — это то, что уже
              случилось, а не то, что предсказывает модель.
            </dd>
          </div>
        </dl>
      </section>

      <section id="api" className="mb-8 rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="mb-3 font-display text-lg font-semibold text-slate-900">API и интеграция</h2>
        <p className="text-sm leading-relaxed text-slate-600">
          Через API можно получать объекты, прогнозы, риски и заявки, принимать
          решения по рискам и обновлять статусы заявок. Параметры запросов, форматы ответов
          и доступные операции описаны в интерактивной документации Swagger.
        </p>
        <div className="my-4 flex flex-wrap items-center gap-3">
          <a
            href="/api/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-sky-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
          >
            Открыть Swagger ↗
          </a>
          <a href="/api/openapi.json" target="_blank" rel="noopener noreferrer" className="text-sm font-medium text-sky-700 hover:underline">
            Схема OpenAPI (JSON) ↗
          </a>
        </div>
        <ol className="list-decimal space-y-2 pl-5 text-sm leading-relaxed text-slate-600">
          <li>Откройте Swagger, нажмите <b>Authorize</b> и введите логин и пароль своей учётной записи.</li>
          <li>Выберите метод, нажмите <b>Try it out</b>, заполните параметры и нажмите <b>Execute</b>.</li>
          <li>
            Для интеграции получите <code>access_token</code> через <code>POST /api/auth/login</code>:
            передайте поля <code>username</code> и <code>password</code> в формате{" "}
            <code className="break-all">application/x-www-form-urlencoded</code>.
            Затем добавляйте токен в заголовок <code>Authorization</code>, как в примере ниже.
          </li>
        </ol>
        <p className="mt-4 text-sm font-medium text-slate-500">Пример: получить первые 10 риск-кейсов</p>
        <pre className="mt-2 overflow-x-auto rounded-xl bg-slate-900 p-4 text-sm leading-relaxed text-slate-100"><code>{apiExample}</code></pre>
        <p className="mt-3 text-sm leading-relaxed text-slate-600">
          Права зависят от роли и настроенного доступа к объектам. Запросы в Swagger
          выполняются в текущей системе: принятие решения или смена статуса заявки сохранит изменения.
        </p>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="mb-4 font-display text-lg font-semibold text-slate-900">Частые вопросы</h2>
        <div className="divide-y divide-slate-100">
          {FAQ.map((f) => (
            <details key={f.q} className="group py-3">
              <summary className="flex cursor-pointer list-none items-center justify-between text-sm font-medium text-slate-900 marker:content-none">
                {f.q}
                <span className="ml-3 shrink-0 text-slate-400 transition-transform group-open:rotate-180">▾</span>
              </summary>
              <p className="mt-2 text-sm text-slate-600">{f.a}</p>
            </details>
          ))}
        </div>
      </section>
    </div>
  );
}
