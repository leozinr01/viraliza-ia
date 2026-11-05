-- =====================================================================
-- VIRALIZA · esquema do banco
-- Cole TUDO no Supabase: SQL Editor > New query > Run
-- Pode rodar mais de uma vez sem problema.
-- =====================================================================

-- ---------- gravações de chat (o notebook grava o chat da Twitch durante a live)
create table if not exists public.gravacoes_chat (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null default auth.uid() references auth.users on delete cascade,
  canal        text not null check (char_length(canal) between 2 and 40),
  status       text not null default 'pedido'
               check (status in ('pedido','gravando','parar','parado','erro')),
  mensagens    int  not null default 0,
  marcadores   int  not null default 0,
  criado_em    timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);

-- ---------- lives (cada pedido de processamento de um VOD)
create table if not exists public.lives (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null default auth.uid() references auth.users on delete cascade,
  fonte        text not null check (fonte ~* '^https://(www\.)?twitch\.tv/videos/\d+'),
  gravacao_id  uuid references public.gravacoes_chat on delete set null,
  teste        boolean not null default false,
  sem_longo    boolean not null default false,
  status       text not null default 'fila'
               check (status in ('fila','processando','pronto','erro','cancelar','cancelado')),
  etapa        int  not null default 0,
  etapa_texto  text,
  detalhe      text,
  titulo       text,
  canal        text,
  longo_url    text,
  longo_download_url text,
  longo_postado boolean not null default false,
  expira_em    timestamptz,
  erro         text,
  criado_em    timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);

-- ---------- cortes verticais
create table if not exists public.cortes (
  id           uuid primary key default gen_random_uuid(),
  live_id      uuid not null references public.lives on delete cascade,
  user_id      uuid not null references auth.users on delete cascade,
  n            int  not null,
  inicio       real, duracao real, nota real,
  marcador     boolean not null default false,
  texto        text,
  titulo       text,
  video_url    text,
  download_url text,
  expira_em    timestamptz,
  tiktok       boolean not null default false,
  shorts       boolean not null default false,
  reels        boolean not null default false,
  descartado   boolean not null default false,
  criado_em    timestamptz not null default now(),
  unique (live_id, n)
);

-- ---------- mensagens do formulário de contato
create table if not exists public.contatos (
  id        uuid primary key default gen_random_uuid(),
  nome      text not null check (char_length(nome) between 1 and 120),
  email     text not null check (email ~* '^[^@\s]+@[^@\s]+\.[^@\s]+$' and char_length(email) <= 200),
  assunto   text check (char_length(assunto) <= 120),
  mensagem  text not null check (char_length(mensagem) between 1 and 5000),
  criado_em timestamptz not null default now()
);

-- ---------- sinal de vida do notebook (pra mostrar "online" no painel)
create table if not exists public.worker (
  id       int primary key default 1 check (id = 1),
  visto_em timestamptz,
  info     text
);
insert into public.worker (id) values (1) on conflict do nothing;

create index if not exists lives_user_idx   on public.lives (user_id, criado_em desc);
create index if not exists lives_status_idx on public.lives (status);
create index if not exists cortes_live_idx  on public.cortes (live_id, n);
create index if not exists cortes_user_idx  on public.cortes (user_id);
create index if not exists grav_user_idx    on public.gravacoes_chat (user_id, criado_em desc);
create index if not exists grav_status_idx  on public.gravacoes_chat (status);

-- ---------- atualizado_em automático
create or replace function public.tocar_atualizado() returns trigger
language plpgsql set search_path = '' as $$
begin new.atualizado_em := now(); return new; end $$;

drop trigger if exists t_lives_upd on public.lives;
create trigger t_lives_upd before update on public.lives for each row execute function public.tocar_atualizado();
drop trigger if exists t_grav_upd on public.gravacoes_chat;
create trigger t_grav_upd before update on public.gravacoes_chat for each row execute function public.tocar_atualizado();

-- =====================================================================
-- SEGURANÇA (RLS): cada usuário só enxerga e mexe no que é dele.
-- O notebook usa a chave secreta, que passa por cima dessas regras.
-- =====================================================================
alter table public.gravacoes_chat enable row level security;
alter table public.lives          enable row level security;
alter table public.cortes         enable row level security;
alter table public.contatos       enable row level security;
alter table public.worker         enable row level security;

-- gravações
drop policy if exists grav_sel on public.gravacoes_chat;
drop policy if exists grav_ins on public.gravacoes_chat;
drop policy if exists grav_upd on public.gravacoes_chat;
drop policy if exists grav_del on public.gravacoes_chat;
create policy grav_sel on public.gravacoes_chat for select to authenticated using (user_id = (select auth.uid()));
create policy grav_ins on public.gravacoes_chat for insert to authenticated
  with check (user_id = (select auth.uid()) and status = 'pedido');
create policy grav_upd on public.gravacoes_chat for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()) and status = 'parar');
create policy grav_del on public.gravacoes_chat for delete to authenticated using (user_id = (select auth.uid()));

-- lives
drop policy if exists lives_sel on public.lives;
drop policy if exists lives_ins on public.lives;
drop policy if exists lives_upd on public.lives;
drop policy if exists lives_del on public.lives;
create policy lives_sel on public.lives for select to authenticated using (user_id = (select auth.uid()));
create policy lives_ins on public.lives for insert to authenticated
  with check (user_id = (select auth.uid()) and status = 'fila');
create policy lives_upd on public.lives for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()) and status in ('fila','cancelar','pronto','erro','cancelado'));
create policy lives_del on public.lives for delete to authenticated using (user_id = (select auth.uid()));

-- o usuário só pode mudar estes campos (o resto quem escreve é o notebook)
revoke update on public.lives from authenticated;
grant  update (status, longo_postado) on public.lives to authenticated;

-- cortes
drop policy if exists cortes_sel on public.cortes;
drop policy if exists cortes_upd on public.cortes;
drop policy if exists cortes_del on public.cortes;
create policy cortes_sel on public.cortes for select to authenticated using (user_id = (select auth.uid()));
create policy cortes_upd on public.cortes for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy cortes_del on public.cortes for delete to authenticated using (user_id = (select auth.uid()));
revoke update on public.cortes from authenticated;
grant  update (titulo, tiktok, shorts, reels, descartado) on public.cortes to authenticated;

-- contato: qualquer visitante pode enviar, ninguém pode ler pelo site
drop policy if exists contatos_ins on public.contatos;
create policy contatos_ins on public.contatos for insert to anon, authenticated with check (true);

-- worker: usuários logados só podem ver se o notebook está online
drop policy if exists worker_sel on public.worker;
create policy worker_sel on public.worker for select to authenticated using (true);
