-- Publicação direta no YouTube, TikTok e Instagram.
-- Rode uma vez no Supabase: SQL Editor > New query > cole tudo > Run.
-- (o mesmo conteúdo também está no final do schema.sql)

-- ---------- contas conectadas (só dados que podem aparecer na tela)
create table if not exists public.conexoes (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references auth.users on delete cascade,
  plataforma    text not null check (plataforma in ('youtube','tiktok','instagram')),
  conta_id      text not null,
  conta_nome    text,
  conta_foto    text,
  criado_em     timestamptz not null default now(),
  atualizado_em timestamptz not null default now(),
  unique (user_id, plataforma)
);

-- ---------- chaves de acesso das contas: só o servidor lê (sem nenhuma policy de RLS)
create table if not exists public.conexoes_tokens (
  conexao_id    uuid primary key references public.conexoes on delete cascade,
  access_token  text not null,
  refresh_token text,
  expira_em     timestamptz,
  atualizado_em timestamptz not null default now()
);

-- ---------- pedidos de publicação (o site cria, o notebook envia)
create table if not exists public.publicacoes (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null default auth.uid() references auth.users on delete cascade,
  plataforma    text not null check (plataforma in ('youtube','tiktok','instagram')),
  corte_id      uuid references public.cortes on delete cascade,
  live_id       uuid references public.lives on delete cascade,   -- vídeo longo (só YouTube)
  titulo        text check (char_length(titulo) <= 100),
  descricao     text check (char_length(descricao) <= 5000),
  privacidade   text not null default 'public' check (privacidade in ('public','unlisted','private')),
  status        text not null default 'fila' check (status in ('fila','enviando','publicado','erro')),
  detalhe       text,
  url           text,
  erro          text,
  criado_em     timestamptz not null default now(),
  atualizado_em timestamptz not null default now(),
  check ((corte_id is null) <> (live_id is null)),
  check (live_id is null or plataforma = 'youtube')
);

create index if not exists pub_status_idx on public.publicacoes (status, criado_em);
create index if not exists pub_user_idx   on public.publicacoes (user_id, criado_em desc);
create index if not exists pub_corte_idx  on public.publicacoes (corte_id);

drop trigger if exists t_con_upd on public.conexoes;
create trigger t_con_upd before update on public.conexoes for each row execute function public.tocar_atualizado();
drop trigger if exists t_tok_upd on public.conexoes_tokens;
create trigger t_tok_upd before update on public.conexoes_tokens for each row execute function public.tocar_atualizado();
drop trigger if exists t_pub_upd on public.publicacoes;
create trigger t_pub_upd before update on public.publicacoes for each row execute function public.tocar_atualizado();

alter table public.conexoes        enable row level security;
alter table public.conexoes_tokens enable row level security;
alter table public.publicacoes     enable row level security;

-- conexões: o usuário vê e desconecta as dele; quem cria é a função "conectar" (chave secreta)
drop policy if exists con_sel on public.conexoes;
drop policy if exists con_del on public.conexoes;
create policy con_sel on public.conexoes for select to authenticated using (user_id = (select auth.uid()));
create policy con_del on public.conexoes for delete to authenticated using (user_id = (select auth.uid()));
revoke insert, update on public.conexoes from anon, authenticated;

-- tokens: ninguém de fora acessa
revoke all on public.conexoes_tokens from anon, authenticated;

-- publicações: o usuário pede (só de vídeos dele) e acompanha; quem atualiza é o notebook
drop policy if exists pub_sel on public.publicacoes;
drop policy if exists pub_ins on public.publicacoes;
drop policy if exists pub_del on public.publicacoes;
create policy pub_sel on public.publicacoes for select to authenticated using (user_id = (select auth.uid()));
create policy pub_ins on public.publicacoes for insert to authenticated
  with check (user_id = (select auth.uid()) and status = 'fila'
    and (corte_id is null or exists (select 1 from public.cortes c where c.id = corte_id and c.user_id = (select auth.uid())))
    and (live_id  is null or exists (select 1 from public.lives  l where l.id = live_id  and l.user_id = (select auth.uid()))));
create policy pub_del on public.publicacoes for delete to authenticated
  using (user_id = (select auth.uid()) and status in ('fila','erro'));
revoke update on public.publicacoes from anon, authenticated;
