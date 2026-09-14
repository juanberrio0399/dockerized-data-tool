import pandas as pd
import pandera as pa
from pandera import Column, DataFrameSchema, Check

# Definir esquema de validación para el CSV
schema = DataFrameSchema({
    # Ajustar según las columnas reales de sample.csv
    # Ejemplo genérico esperando columnas numéricas o de texto estándar
})

def load_and_validate_data(filepath):
    try:
        df = pd.read_csv(filepath)
        # Validar el DataFrame contra el esquema
        validated_df = schema.validate(df, lazy=True)
        return validated_df
    except pa.errors.SchemaErrors as err:
        print("Error de validación en el esquema de datos:")
        print(err.failure_cases)
        raise SystemExit(1)
    except Exception as e:
        print(f"Error al cargar el archivo: {e}")
        raise SystemExit(1)

if __name__ == "__main__":
    load_and_validate_data("sample.csv")
