TYPE=VIEW
query=select curdate() AS `fecha_cierre`,count(0) AS `total_vehiculos_atendidos`,ifnull(sum(`taller_automotriz_db`.`ordenes_trabajo`.`total`),0.00) AS `total_ingresos_efectivo` from `taller_automotriz_db`.`ordenes_trabajo` where cast(coalesce(`taller_automotriz_db`.`ordenes_trabajo`.`fecha_cierre`,`taller_automotriz_db`.`ordenes_trabajo`.`fecha_ingreso`) as date) = curdate() and `taller_automotriz_db`.`ordenes_trabajo`.`estado` = \'Entregado\'
md5=d4952b3b58de47c6f0b6a834ce356f3b
updatable=0
algorithm=0
definer_user=root
definer_host=localhost
suid=2
with_check_option=0
timestamp=0001788102243029454
create-version=2
source=SELECT \n    CURDATE() AS fecha_cierre,\n    COUNT(*) AS total_vehiculos_atendidos,\n    IFNULL(SUM(total), 0.00) AS total_ingresos_efectivo\nFROM ordenes_trabajo\nWHERE DATE(COALESCE(fecha_cierre, fecha_ingreso)) = CURDATE() \n    AND estado = \'Entregado\'
client_cs_name=utf8mb4
connection_cl_name=utf8mb4_unicode_ci
view_body_utf8=select curdate() AS `fecha_cierre`,count(0) AS `total_vehiculos_atendidos`,ifnull(sum(`taller_automotriz_db`.`ordenes_trabajo`.`total`),0.00) AS `total_ingresos_efectivo` from `taller_automotriz_db`.`ordenes_trabajo` where cast(coalesce(`taller_automotriz_db`.`ordenes_trabajo`.`fecha_cierre`,`taller_automotriz_db`.`ordenes_trabajo`.`fecha_ingreso`) as date) = curdate() and `taller_automotriz_db`.`ordenes_trabajo`.`estado` = \'Entregado\'
mariadb-version=100432
