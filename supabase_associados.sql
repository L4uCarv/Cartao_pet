-- Execute este script no SQL Editor do Supabase.
create table if not exists public.associados (
    id uuid primary key default gen_random_uuid(),
    criador_id uuid not null references public.tutores(id) on delete cascade,
    nome text not null,
    telefone text not null,
    endereco text not null,
    grupo_numero integer not null,
    created_at timestamptz not null default now()
);

alter table public.pets
    add column if not exists associado_id uuid references public.associados(id) on delete set null;

alter table public.associados enable row level security;

create policy "Criadores gerenciam os seus associados"
on public.associados
for all
using (criador_id = auth.uid())
with check (criador_id = auth.uid());