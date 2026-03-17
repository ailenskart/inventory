/*
    Singular test: for completed transfers, out qty must equal in qty.
    Each transfer_id should have balanced out/in pairs.
*/
with balance as (
    select
        transfer_id,
        sum(case when transfer_direction = 'out' then transfer_qty else 0 end) as total_out,
        sum(case when transfer_direction = 'in' then transfer_qty else 0 end) as total_in
    from {{ ref('stg_transfers_daily') }}
    where status = 'received'
    group by transfer_id
)

select * from balance
where total_out != total_in
