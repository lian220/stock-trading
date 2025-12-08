# Supabase 클라이언트 설정
import os
from supabase import create_client, Client
import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Model
from tensorflow.keras.layers import (
    Input, Dense, Dropout, LayerNormalization, MultiHeadAttention, Add, GlobalAveragePooling1D
)
import tensorflow as tf
from tensorflow.keras.optimizers import Adam
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

import json
from sklearn.metrics import mean_absolute_error, mean_squared_error

# Supabase 연결 설정
url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(url, key)

# Supabase에서 데이터 가져오기
# def get_stock_data_from_db():
#     try:
#         response = supabase.table("economic_and_stock_data").select("*").order("날짜", desc=False).execute()
#         print(f"economic_and_stock_data 테이블에서 {len(response.data)}개 데이터를 성공적으로 가져왔습니다!")
#         print(response.data)
#         # 응답 데이터를 DataFrame으로 변환
#         df = pd.DataFrame(response.data)

#         # 날짜 열을 datetime으로 변환
#         df['날짜'] = pd.to_datetime(df['날짜'])
#         df.sort_values(by='날짜', inplace=True)

#         print("Handling missing values and filtering invalid data...")
#         df.fillna(method='ffill', inplace=True)
#         df.fillna(method='bfill', inplace=True)
#         df = df.apply(pd.to_numeric, errors='coerce')
#         df.dropna(inplace=True)

#         return df
#     except Exception as e:
#         print(f"데이터 가져오기 오류: {e}")
#         return None

def get_stock_data_from_db():
    try:
        # 전체 데이터 가져오기
        all_data = get_all_data("economic_and_stock_data")
        print(f"economic_and_stock_data 테이블에서 {len(all_data)}개 데이터를 성공적으로 가져왔습니다!")
        
        if len(all_data) == 0:
            print("경고: 데이터가 없습니다!")
            return pd.DataFrame()
        
        df = pd.DataFrame(all_data)
        print(f"DataFrame 생성 완료: {df.shape} (행, 열)")
        print(f"컬럼 수: {len(df.columns)}")
        print(f"컬럼명 샘플: {list(df.columns[:10])}")

        # 날짜 열을 datetime으로 변환하고 정렬
        if '날짜' not in df.columns:
            print("경고: '날짜' 컬럼이 없습니다!")
            return pd.DataFrame()
        
        df['날짜'] = pd.to_datetime(df['날짜'])
        df.sort_values(by='날짜', inplace=True)
        print(f"날짜 범위: {df['날짜'].min()} ~ {df['날짜'].max()}")
        
        # 원본 데이터에서 NULL/None 값 확인 (데이터베이스에서 가져온 직후)
        print("\n=== 원본 데이터 NULL/None 값 확인 ===")
        null_counts_raw = df.isnull().sum()
        none_counts = 0
        for col in df.columns:
            if col != '날짜':
                none_count = sum(1 for val in df[col] if val is None)
                if none_count > 0:
                    none_counts += none_count
                    print(f"  {col}: {none_count}개의 None 값")
        
        if none_counts > 0:
            print(f"총 {none_counts}개의 None 값이 발견되었습니다. None을 NaN으로 변환합니다.")
            df = df.replace([None], np.nan)
        
        null_after = df.isnull().sum().sum()
        if null_after > 0:
            print(f"변환 후 총 {null_after}개의 NULL/NaN 값이 있습니다.")

        # 수치형 컬럼으로 변환 (결측치 처리 전에 먼저 확인)
        exclude_columns = ['날짜']
        numeric_columns = [col for col in df.columns if col not in exclude_columns]
        print(f"수치형 컬럼 수: {len(numeric_columns)}")
        
        # 원본 데이터의 NaN 비율 확인 (결측치 처리 전)
        print("\n=== 결측치 처리 전 NaN 비율 ===")
        df_numeric = df[numeric_columns].apply(pd.to_numeric, errors='coerce')
        nan_ratios_before = df_numeric.isna().mean()
        print(f"NaN이 있는 컬럼 수: {(nan_ratios_before > 0).sum()}")
        
        # NaN 비율이 높은 컬럼 상세 정보 출력
        if (nan_ratios_before > 0).any():
            print("\nNaN 비율이 높은 컬럼 (상위 20개):")
            high_nan_cols = nan_ratios_before[nan_ratios_before > 0].sort_values(ascending=False).head(20)
            for col, ratio in high_nan_cols.items():
                nan_count = df_numeric[col].isna().sum()
                total_count = len(df_numeric)
                print(f"  {col}: {ratio:.1%} ({nan_count}/{total_count}개)")
        else:
            print("모든 컬럼에 NaN이 없습니다 (또는 모든 값이 NaN입니다)")
        
        # 실제 데이터가 있는지 확인 (모든 값이 NaN인지)
        non_null_counts = df_numeric.notna().sum()
        print(f"\n실제 데이터가 있는 행 수 (컬럼별, 상위 10개):")
        print(non_null_counts.nlargest(10))
        print(f"최대 행 수: {len(df)}")
        
        # 데이터가 전혀 없는 컬럼 확인
        completely_empty = non_null_counts[non_null_counts == 0]
        if len(completely_empty) > 0:
            print(f"\n경고: {len(completely_empty)}개 컬럼이 완전히 비어있습니다:")
            print(f"  {list(completely_empty.index[:10])}")
        
        # 결측치 처리
        print("\n결측치 처리 중...")
        df[numeric_columns] = df_numeric
        
        # 단계별 결측치 처리
        # 1단계: 앞으로 채우기 (forward fill)
        print("  1단계: 앞 값으로 채우기 (ffill)...")
        df[numeric_columns] = df[numeric_columns].ffill()
        
        # 2단계: 뒤로 채우기 (backward fill)
        print("  2단계: 뒤 값으로 채우기 (bfill)...")
        df[numeric_columns] = df[numeric_columns].bfill()
        
        # 3단계: 여전히 NaN인 경우 컬럼별 평균값으로 채우기
        remaining_nan = df[numeric_columns].isna().sum().sum()
        if remaining_nan > 0:
            print(f"  3단계: {remaining_nan}개의 NaN이 남아있어 컬럼별 평균값으로 채우기...")
            for col in numeric_columns:
                if df[col].isna().any():
                    col_mean = df[col].mean()
                    if pd.notna(col_mean):
                        df[col] = df[col].fillna(col_mean)
                    else:
                        # 평균도 NaN이면 0으로 채우기
                        df[col] = df[col].fillna(0)
        
        # 4단계: 최종적으로 남은 NaN은 0으로 채우기
        final_nan_before_zero = df[numeric_columns].isna().sum().sum()
        if final_nan_before_zero > 0:
            print(f"  4단계: {final_nan_before_zero}개의 NaN을 0으로 채우기...")
            df[numeric_columns] = df[numeric_columns].fillna(0)

        # NaN 비율 확인 (결측치 처리 후)
        nan_ratios = df[numeric_columns].isna().mean()
        print("\n=== 결측치 처리 후 NaN 비율 ===")
        print(f"NaN이 있는 컬럼 수: {(nan_ratios > 0).sum()}")
        if (nan_ratios > 0).any():
            print("NaN 비율이 0보다 큰 컬럼:")
            print(nan_ratios[nan_ratios > 0].head(10))
        else:
            print("모든 컬럼의 NaN 비율: 0.0 (결측치 처리 완료)")

        # 유효한 데이터가 있는 컬럼만 dropna 대상으로 설정
        valid_columns = [col for col in numeric_columns if nan_ratios[col] < 1.0]
        print(f"\n유효한 컬럼 수: {len(valid_columns)} / {len(numeric_columns)}")
        
        # 완전히 비어있는 컬럼 제거 (모든 값이 NaN인 컬럼)
        empty_columns = [col for col in numeric_columns if nan_ratios[col] >= 1.0]
        if empty_columns:
            print(f"경고: 다음 {len(empty_columns)}개 컬럼이 완전히 비어있어 제외됩니다:")
            print(f"  {empty_columns[:10]}...")
            df = df.drop(columns=empty_columns)
            numeric_columns = [col for col in numeric_columns if col not in empty_columns]
        
        if len(valid_columns) > 0:
            df.dropna(subset=valid_columns, inplace=True)
        else:
            print("경고: 유효한 컬럼이 없습니다!")

        # 최종 NaN 확인
        final_nan_check = df[numeric_columns].isna().sum().sum()
        if final_nan_check > 0:
            print(f"\n경고: 최종 처리 후에도 {final_nan_check}개의 NaN이 남아있습니다.")
            print("남은 NaN을 0으로 채우는 중...")
            df[numeric_columns] = df[numeric_columns].fillna(0)
        else:
            print("\n모든 NaN 값이 성공적으로 처리되었습니다.")

        print(f"\n처리 후 데이터 크기: {df.shape}")
        print(f"남은 행 수: {len(df)}")
        print(f"최종 컬럼 수: {len(df.columns)}")
        
        return df
    except Exception as e:
        print(f"데이터 가져오기 오류: {e}")
        import traceback
        traceback.print_exc()
        return None

def get_all_data(table_name):
    all_data = []
    offset = 0
    limit = 1000  # Supabase의 기본 제한
    while True:
        response = supabase.table(table_name).select("*").order("날짜", desc=False).limit(limit).offset(offset).execute()
        data = response.data
        if not data:  # 더 이상 데이터가 없으면 종료
            break
        all_data.extend(data)
        offset += limit
    return all_data

# Transformer Encoder 정의
def transformer_encoder(inputs, num_heads, ff_dim, dropout=0.1):
    attention_output = MultiHeadAttention(num_heads=num_heads, key_dim=inputs.shape[-1])(inputs, inputs)
    attention_output = Dropout(dropout)(attention_output)
    attention_output = Add()([inputs, attention_output])
    attention_output = LayerNormalization(epsilon=1e-6)(attention_output)

    ffn = Dense(ff_dim, activation="relu")(attention_output)
    ffn = Dense(inputs.shape[-1])(ffn)
    ffn_output = Dropout(dropout)(ffn)
    ffn_output = Add()([attention_output, ffn_output])
    ffn_output = LayerNormalization(epsilon=1e-6)(ffn_output)

    return ffn_output

# Transformer 모델 정의
def build_transformer_with_two_inputs(stock_shape, econ_shape, num_heads, ff_dim, target_size):
    stock_inputs = Input(shape=stock_shape)
    stock_encoded = stock_inputs
    for _ in range(4):  # 4개의 Transformer Layer
        stock_encoded = transformer_encoder(stock_encoded, num_heads=num_heads, ff_dim=ff_dim)
    stock_encoded = Dense(64, activation="relu")(stock_encoded)

    econ_inputs = Input(shape=econ_shape)
    econ_encoded = econ_inputs
    for _ in range(4):  # 4개의 Transformer Layer
        econ_encoded = transformer_encoder(econ_encoded, num_heads=num_heads, ff_dim=ff_dim)
    econ_encoded = Dense(64, activation="relu")(econ_encoded)

    merged = Add()([stock_encoded, econ_encoded])
    merged = Dense(128, activation="relu")(merged)
    merged = Dropout(0.2)(merged)
    merged = GlobalAveragePooling1D()(merged)
    outputs = Dense(target_size)(merged)

    return Model(inputs=[stock_inputs, econ_inputs], outputs=outputs)

####################################
# [1단계] 모델 학습 및 예측 부분
# 이 부분이 실행되어야 predicted_stocks 테이블에 데이터가 생성됩니다!
####################################
print("=" * 60)
print("[1단계] 모델 학습 및 예측 시작")
print("=" * 60)
print("Loading data from database...")
data = get_stock_data_from_db()
if data is None or data.empty:
    raise ValueError("DB에서 데이터를 가져오지 못했습니다. 테이블과 컬럼명을 확인하세요.")

# data.sort_values(by='날짜', inplace=True)

# print("Handling missing values and filtering invalid data...")
# data.fillna(method='ffill', inplace=True)
# data.fillna(method='bfill', inplace=True)
# data = data.apply(pd.to_numeric, errors='coerce')
# data.dropna(inplace=True)

forecast_horizon = 14  # 예측 기간 (14일 후를 예측)

# DB에서 활성화된 주식 목록 조회
def get_target_columns_from_db():
    """stock_ticker_mapping 테이블에서 활성화된 주식명 목록을 가져옵니다."""
    try:
        response = supabase.table("stock_ticker_mapping").select("stock_name, is_etf").eq("is_active", True).execute()
        
        if not response.data:
            print("경고: stock_ticker_mapping 테이블에서 활성화된 주식을 찾을 수 없습니다.")
            print("기본 주식 목록을 사용합니다.")
            # 기본값 반환 (fallback)
            return [
                '애플', '마이크로소프트', '아마존', '구글 A', '구글 C', '메타',
                '테슬라', '엔비디아', '인텔', '마이크론', '브로드컴',
                '텍사스 인스트루먼트', 'AMD', '어플라이드 머티리얼즈',
                '셀레스티카', '버티브 홀딩스', '비스트라 에너지', '블룸에너지', '오클로', '팔란티어',
                '세일즈포스', '오라클', '앱플로빈', '팔로알토 네트웍스', '크라우드 스트라이크',
                '스노우플레이크', 'TSMC', '크리도 테크놀로지 그룹 홀딩', '로빈후드', '일라이릴리',
                '월마트', '존슨앤존슨', 'S&P 500 ETF', 'QQQ ETF'
            ]
        
        # 주식명 목록 추출 (ETF 포함)
        target_columns = [item["stock_name"] for item in response.data]
        
        print(f"DB에서 {len(target_columns)}개의 활성화된 주식을 가져왔습니다.")
        print(f"주식 목록: {target_columns[:10]}... (총 {len(target_columns)}개)")
        
        return target_columns
    except Exception as e:
        print(f"DB에서 주식 목록 조회 중 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()
        # 오류 발생 시 기본값 반환
        return [
            '애플', '마이크로소프트', '아마존', '구글 A', '구글 C', '메타',
            '테슬라', '엔비디아', '인텔', '마이크론', '브로드컴',
            '텍사스 인스트루먼트', 'AMD', '어플라이드 머티리얼즈',
            '셀레스티카', '버티브 홀딩스', '비스트라 에너지', '블룸에너지', '오클로', '팔란티어',
            '세일즈포스', '오라클', '앱플로빈', '팔로알토 네트웍스', '크라우드 스트라이크',
            '스노우플레이크', 'TSMC', '크리도 테크놀로지 그룹 홀딩', '로빈후드', '일라이릴리',
            '월마트', '존슨앤존슨', 'S&P 500 ETF', 'QQQ ETF'
        ]

target_columns = get_target_columns_from_db()

economic_features = [
    '10년 기대 인플레이션율', '장단기 금리차', '기준금리', '미시간대 소비자 심리지수',
    '실업률', '2년 만기 미국 국채 수익률', '10년 만기 미국 국채 수익률', '금융스트레스지수',
    '개인 소비 지출', '소비자 물가지수', '5년 변동금리 모기지', '미국 달러 환율',
    '통화 공급량 M2', '가계 부채 비율', 'GDP 성장률', '나스닥 종합지수', 'S&P 500 지수', '금 가격', '달러 인덱스', '나스닥 100',
    'S&P 500 ETF', 'QQQ ETF', '러셀 2000 ETF', '다우 존스 ETF', 'VIX 지수',
    '닛케이 225', '상해종합', '항셍', '영국 FTSE', '독일 DAX', '프랑스 CAC 40',
    '미국 전체 채권시장 ETF', 'TIPS ETF', '투자등급 회사채 ETF', '달러/엔', '달러/위안',
    '미국 리츠 ETF'
]

print("Scaling data...")

# 컬럼 존재 여부 및 데이터 유효성 검증
print("\n=== 컬럼 존재 여부 검증 ===")
available_target_columns = [col for col in target_columns if col in data.columns]
missing_target_columns = [col for col in target_columns if col not in data.columns]

available_econ_features = [col for col in economic_features if col in data.columns]
missing_econ_features = [col for col in economic_features if col not in data.columns]

print(f"사용 가능한 주식 컬럼: {len(available_target_columns)}/{len(target_columns)}")
if missing_target_columns:
    print(f"경고: 다음 주식 컬럼이 데이터에 없습니다: {missing_target_columns[:10]}...")
    
print(f"사용 가능한 경제 지표 컬럼: {len(available_econ_features)}/{len(economic_features)}")
if missing_econ_features:
    print(f"경고: 다음 경제 지표 컬럼이 데이터에 없습니다: {missing_econ_features[:10]}...")

# 사용 가능한 컬럼만 사용
if len(available_target_columns) == 0:
    raise ValueError("사용 가능한 주식 컬럼이 없습니다. 데이터베이스의 컬럼명을 확인하세요.")
if len(available_econ_features) == 0:
    raise ValueError("사용 가능한 경제 지표 컬럼이 없습니다. 데이터베이스의 컬럼명을 확인하세요.")

# target_columns와 economic_features를 사용 가능한 컬럼만으로 업데이트
target_columns = available_target_columns
economic_features = available_econ_features

print(f"\n최종 사용할 주식 컬럼 수: {len(target_columns)}")
print(f"최종 사용할 경제 지표 컬럼 수: {len(economic_features)}")

# NaN 값 확인 및 처리
print("\n=== 스케일링 전 NaN 값 확인 ===")
target_nan_counts = data[target_columns].isna().sum()
econ_nan_counts = data[economic_features].isna().sum()

if target_nan_counts.sum() > 0:
    print(f"경고: 주식 컬럼에 {target_nan_counts.sum()}개의 NaN이 있습니다.")
    print("NaN이 많은 컬럼 (상위 5개):")
    print(target_nan_counts.nlargest(5))
    
if econ_nan_counts.sum() > 0:
    print(f"경고: 경제 지표 컬럼에 {econ_nan_counts.sum()}개의 NaN이 있습니다.")
    print("NaN이 많은 컬럼 (상위 5개):")
    print(econ_nan_counts.nlargest(5))

# NaN이 있는 경우 추가 처리 (ffill, bfill로 이미 처리했지만 재확인)
data[target_columns] = data[target_columns].ffill().bfill()
data[economic_features] = data[economic_features].ffill().bfill()

# 여전히 NaN이 있는 컬럼은 0으로 채우기 (마지막 수단)
data[target_columns] = data[target_columns].fillna(0)
data[economic_features] = data[economic_features].fillna(0)

# 최종 NaN 확인
final_target_nan = data[target_columns].isna().sum().sum()
final_econ_nan = data[economic_features].isna().sum().sum()
if final_target_nan > 0 or final_econ_nan > 0:
    print(f"경고: 여전히 NaN이 남아있습니다. (주식: {final_target_nan}, 경제: {final_econ_nan})")
else:
    print("모든 NaN 값이 처리되었습니다.")

train_size = int(len(data) * 0.8)
train_data = data.iloc[:train_size]
test_data = data.iloc[train_size:]

data_scaled = data.copy()
stock_scaler = MinMaxScaler()
econ_scaler = MinMaxScaler()

# 스케일링 수행 (NaN이 없는 상태)
try:
    data_scaled[target_columns] = stock_scaler.fit_transform(data[target_columns])
    data_scaled[economic_features] = econ_scaler.fit_transform(data[economic_features])
    print("스케일링 완료")
except Exception as e:
    print(f"스케일링 오류: {e}")
    print("스케일링 전 데이터 상태:")
    print(f"주식 컬럼 NaN 수: {data[target_columns].isna().sum().sum()}")
    print(f"경제 지표 컬럼 NaN 수: {data[economic_features].isna().sum().sum()}")
    raise

lookback = 90

# 훈련 데이터 생성
X_stock_train = []
X_econ_train = []
y_train = []

for i in range(lookback, len(data_scaled) - forecast_horizon):
    X_stock_seq = data_scaled[target_columns].iloc[i - lookback:i].to_numpy()
    X_econ_seq = data_scaled[economic_features].iloc[i - lookback:i].to_numpy()
    y_val = data_scaled[target_columns].iloc[i + forecast_horizon - 1].to_numpy()
    X_stock_train.append(X_stock_seq)
    X_econ_train.append(X_econ_seq)
    y_train.append(y_val)

X_stock_train = np.array(X_stock_train)
X_econ_train = np.array(X_econ_train)
y_train = np.array(y_train)

# 전체 예측 데이터 생성: 마지막 날짜까지 포함하여 예측 (미래 실제값 없어도 예측)
X_stock_full = []
X_econ_full = []
for i in range(lookback, len(data_scaled)):  # 여기서 forecast_horizon 빼지 않음
    X_stock_seq = data_scaled[target_columns].iloc[i - lookback:i].to_numpy()
    X_econ_seq = data_scaled[economic_features].iloc[i - lookback:i].to_numpy()
    X_stock_full.append(X_stock_seq)
    X_econ_full.append(X_econ_seq)

X_stock_full = np.array(X_stock_full)
X_econ_full = np.array(X_econ_full)

print("Building Transformer model...")
stock_shape = (lookback, len(target_columns))
econ_shape = (lookback, len(economic_features))

model = build_transformer_with_two_inputs(stock_shape, econ_shape, num_heads=8, ff_dim=256, target_size=len(target_columns))
model.compile(optimizer=Adam(learning_rate=0.0001), loss='mse', metrics=['mae'])
model.summary()

print("Training model...")
history = model.fit([X_stock_train, X_econ_train], y_train, epochs=50, batch_size=32, verbose=1)

print("Performing full predictions...")
predicted_prices = model.predict([X_stock_full, X_econ_full], verbose=1)
predicted_prices_actual = stock_scaler.inverse_transform(predicted_prices)

pred_len = len(predicted_prices_actual)

# 실제로 사용 가능한 데이터 길이 계산
available_data_len = len(data) - lookback
actual_pred_len = min(pred_len, available_data_len)

print(f"예측 데이터 길이: {pred_len}")
print(f"사용 가능한 실제 데이터 길이: {available_data_len}")
print(f"최종 사용할 길이: {actual_pred_len}")

# 예측 데이터를 실제 데이터 길이에 맞춤 (뒤에서 자름)
predicted_prices_actual = predicted_prices_actual[:actual_pred_len]

# 오늘 날짜들 (실제 데이터가 있는 범위만)
today_dates = data['날짜'].iloc[lookback : lookback + actual_pred_len].values

# 오늘 실제 주가 (실제 데이터가 있는 범위만)
actual_full = data[target_columns].iloc[lookback : lookback + actual_pred_len].values

print(f"실제 데이터 shape: {actual_full.shape}")
print(f"예측 데이터 shape: {predicted_prices_actual.shape}")

# NaN 값 확인
print("\n=== 예측 결과 NaN 확인 ===")
predicted_nan_count = np.isnan(predicted_prices_actual).sum()
actual_nan_count = np.isnan(actual_full).sum()
print(f"예측값 NaN 개수: {predicted_nan_count}")
print(f"실제값 NaN 개수: {actual_nan_count}")

if predicted_nan_count > 0:
    print("경고: 예측값에 NaN이 포함되어 있습니다!")
    # NaN이 있는 행/열 확인
    nan_rows, nan_cols = np.where(np.isnan(predicted_prices_actual))
    print(f"NaN이 있는 위치: {len(set(nan_rows))}개 행, {len(set(nan_cols))}개 열")
    
if actual_nan_count > 0:
    print("경고: 실제값에 NaN이 포함되어 있습니다!")
    # NaN이 있는 행/열 확인
    nan_rows, nan_cols = np.where(np.isnan(actual_full))
    print(f"NaN이 있는 위치: {len(set(nan_rows))}개 행, {len(set(nan_cols))}개 열")

# pred_len을 실제 사용할 길이로 업데이트
pred_len = actual_pred_len

result_data = pd.DataFrame({'날짜': today_dates})

for idx, col in enumerate(target_columns):
    pred_values = predicted_prices_actual[:, idx]
    actual_values = actual_full[:, idx]
    
    # NaN이 있는 경우 경고 및 처리
    if np.isnan(pred_values).any():
        nan_count = np.isnan(pred_values).sum()
        print(f"경고: {col}_Predicted에 {nan_count}개의 NaN이 있습니다.")
        # NaN을 0으로 채우거나 이전 값으로 보간
        pred_series = pd.Series(pred_values)
        pred_values = pred_series.ffill().bfill().fillna(0).values
    
    if np.isnan(actual_values).any():
        nan_count = np.isnan(actual_values).sum()
        print(f"경고: {col}_Actual에 {nan_count}개의 NaN이 있습니다.")
        # NaN을 0으로 채우거나 이전 값으로 보간
        actual_series = pd.Series(actual_values)
        actual_values = actual_series.ffill().bfill().fillna(0).values
    
    result_data[f'{col}_Predicted'] = pred_values
    result_data[f'{col}_Actual'] = actual_values

result_data['날짜'] = pd.to_datetime(result_data['날짜'], errors='coerce')
result_data['날짜'] = result_data['날짜'].dt.strftime('%Y-%m-%d')

# 최종 결과 데이터 검증
print("\n=== 최종 결과 데이터 검증 ===")
print(f"결과 데이터 shape: {result_data.shape}")
print(f"컬럼 수: {len(result_data.columns)}")

# Predicted 컬럼과 Actual 컬럼 확인
predicted_cols = [col for col in result_data.columns if '_Predicted' in col]
actual_cols = [col for col in result_data.columns if '_Actual' in col]
print(f"Predicted 컬럼 수: {len(predicted_cols)}")
print(f"Actual 컬럼 수: {len(actual_cols)}")

# 각 컬럼별 데이터 샘플 확인
print("\n=== 예측 결과 샘플 (첫 5개 행) ===")
if len(predicted_cols) > 0:
    print("Predicted 값 샘플:")
    for col in predicted_cols[:3]:  # 처음 3개만
        sample_values = result_data[col].head(5).values
        print(f"  {col}: {sample_values}")
        nan_count = result_data[col].isna().sum()
        if nan_count > 0:
            print(f"    ⚠️ {nan_count}개의 NaN 발견!")

if len(actual_cols) > 0:
    print("\nActual 값 샘플:")
    for col in actual_cols[:3]:  # 처음 3개만
        sample_values = result_data[col].head(5).values
        print(f"  {col}: {sample_values}")
        nan_count = result_data[col].isna().sum()
        if nan_count > 0:
            print(f"    ⚠️ {nan_count}개의 NaN 발견!")

final_nan_count = result_data.isna().sum().sum()
print(f"\n결과 데이터의 총 NaN 개수: {final_nan_count}")

if final_nan_count > 0:
    print("\n⚠️ NaN이 있는 컬럼 상세:")
    nan_columns = result_data.columns[result_data.isna().any()].tolist()
    for col in nan_columns:
        nan_count = result_data[col].isna().sum()
        total_count = len(result_data)
        print(f"  - {col}: {nan_count}/{total_count}개 ({nan_count/total_count*100:.1f}%)")
    
    print("\nNaN 값을 처리하는 중...")
    # Predicted 컬럼의 NaN은 이전 예측값으로 채우거나 평균값으로 채우기
    for col in predicted_cols:
        if result_data[col].isna().any():
            # 먼저 ffill, bfill 시도
            result_data[col] = result_data[col].ffill().bfill()
            # 여전히 NaN이면 평균값으로 채우기
            if result_data[col].isna().any():
                col_mean = result_data[col].mean()
                if pd.notna(col_mean):
                    result_data[col] = result_data[col].fillna(col_mean)
                else:
                    # 평균도 없으면 0으로
                    result_data[col] = result_data[col].fillna(0)
    
    # Actual 컬럼의 NaN도 처리
    for col in actual_cols:
        if result_data[col].isna().any():
            result_data[col] = result_data[col].ffill().bfill().fillna(0)
    
    # 최종적으로 남은 NaN은 모두 0으로
    result_data = result_data.fillna(0)
    
    # 최종 확인
    remaining_nan = result_data.isna().sum().sum()
    if remaining_nan > 0:
        print(f"⚠️ 경고: {remaining_nan}개의 NaN이 여전히 남아있습니다!")
    else:
        print("✅ 모든 NaN 값이 처리되었습니다.")
else:
    print("✅ 모든 데이터가 유효합니다.")

# # 결과를 Supabase에 저장
def save_predictions_to_db(result_df):
    try:
        # 입력 데이터 검증
        if result_df is None or len(result_df) == 0:
            print("경고: 저장할 데이터가 없습니다.")
            return False

        # 저장 전 최종 검증
        print("\n=== 저장 전 최종 검증 ===")
        print(f"DataFrame shape: {result_df.shape}")
        
        # Predicted 컬럼 확인
        predicted_cols = [col for col in result_df.columns if '_Predicted' in col]
        actual_cols = [col for col in result_df.columns if '_Actual' in col]
        
        print(f"Predicted 컬럼 수: {len(predicted_cols)}")
        print(f"Actual 컬럼 수: {len(actual_cols)}")
        
        # Predicted 컬럼의 유효성 확인
        for col in predicted_cols:
            nan_count = result_df[col].isna().sum()
            null_count = (result_df[col] == None).sum() if None in result_df[col].values else 0
            if nan_count > 0 or null_count > 0:
                print(f"⚠️ 경고: {col}에 {nan_count}개 NaN, {null_count}개 None이 있습니다!")
            else:
                # 값이 있는지 확인
                valid_count = result_df[col].notna().sum()
                if valid_count == 0:
                    print(f"⚠️ 경고: {col}에 유효한 값이 없습니다!")
                else:
                    sample_val = result_df[col].iloc[0]
                    print(f"  ✓ {col}: {valid_count}개 유효값, 샘플: {sample_val}")
        
        # NaN 값을 None으로 변환 (JSON 직렬화를 위해 필수)
        # Supabase는 NaN을 지원하지 않으므로 None(null)로 변환해야 함
        result_df_clean = result_df.copy()
        
        # 먼저 모든 NaN을 확인하고 로그 출력
        nan_count_before = result_df_clean.isna().sum().sum()
        if nan_count_before > 0:
            print(f"⚠️ 경고: {nan_count_before}개의 NaN이 발견되었습니다. 0으로 채운 후 저장합니다.")
            result_df_clean = result_df_clean.fillna(0)
        
        # inf 값도 처리
        result_df_clean = result_df_clean.replace([np.inf, -np.inf], 0)
        
        # 기존 테이블이 없으면 생성 (predicted_stocks 테이블에 저장)
        records = result_df_clean.to_dict('records')
        print(f"저장할 레코드 수: {len(records)}")
        
        # 첫 번째 레코드 샘플 확인
        if len(records) > 0:
            first_record = records[0]
            predicted_in_first = {k: v for k, v in first_record.items() if '_Predicted' in k}
            print(f"\n첫 번째 레코드의 Predicted 값 샘플 (처음 5개):")
            for i, (key, val) in enumerate(list(predicted_in_first.items())[:5]):
                print(f"  {key}: {val} (type: {type(val).__name__})")
                if val is None or (isinstance(val, float) and np.isnan(val)):
                    print(f"    ⚠️ 이 값이 NULL로 저장될 것입니다!")

        # 테이블에 먼저 데이터 삭제 후 새로 삽입
        delete_response = supabase.table("predicted_stocks").delete().neq("id", 0).execute()
        print(f"기존 데이터 삭제 완료")

        # 일괄 삽입 (큰 데이터라면 청크로 나누어 삽입)
        chunk_size = 100
        total_inserted = 0
        for i in range(0, len(records), chunk_size):
            chunk = records[i:i+chunk_size]
            
            # 각 청크의 NaN/None 값을 0으로 변환 (이중 안전장치)
            # ⚠️ 중요: None으로 변환하면 DB에 NULL로 저장되므로 0으로 변환
            for record in chunk:
                for key, value in record.items():
                    # Predicted/Actual 컬럼의 경우 None이나 NaN을 0으로 변환
                    if '_Predicted' in key or '_Actual' in key:
                        if value is None:
                            print(f"⚠️ 경고: {key}에 None 값 발견! 0으로 변환합니다.")
                            record[key] = 0
                        elif isinstance(value, (float, np.floating)):
                            if np.isnan(value):
                                print(f"⚠️ 경고: {key}에 NaN 값 발견! 0으로 변환합니다.")
                                record[key] = 0
                            elif np.isinf(value):
                                print(f"⚠️ 경고: {key}에 Inf 값 발견! 0으로 변환합니다.")
                                record[key] = 0
            
            try:
                response = supabase.table("predicted_stocks").insert(chunk).execute()
                total_inserted += len(chunk)
                print(f"청크 {i//chunk_size + 1}: {len(chunk)}개 레코드 삽입 완료")
            except Exception as chunk_error:
                print(f"청크 {i//chunk_size + 1} 삽입 실패: {chunk_error}")
                print(f"문제가 있는 청크의 첫 번째 레코드 샘플: {chunk[0] if chunk else 'None'}")
                # 첫 번째 레코드의 Predicted 값 확인
                if chunk and len(chunk) > 0:
                    first_predicted = {k: v for k, v in chunk[0].items() if '_Predicted' in k}
                    print(f"첫 번째 레코드의 Predicted 값: {dict(list(first_predicted.items())[:5])}")
                raise

        print(f"총 {total_inserted}개의 예측 결과가 데이터베이스에 저장되었습니다.")
        
        # 저장 확인
        count_response = supabase.table("predicted_stocks").select("id", count="exact").execute()
        saved_count = count_response.count
        print(f"저장 확인: predicted_stocks 테이블에 {saved_count}개 레코드가 있습니다.")
        
        return True
    except Exception as e:
        print(f"데이터베이스 저장 오류: {e}")
        import traceback
        traceback.print_exc()
        return False

# [중요] 예측 결과를 predicted_stocks 테이블에 저장
# 이 부분이 실행되어야 predicted_stocks 테이블에 데이터가 생성됩니다!
print("=" * 60)
print("[1단계 완료] 예측 결과를 predicted_stocks 테이블에 저장 중...")
print("=" * 60)
save_success = save_predictions_to_db(result_data)
if not save_success:
    print("경고: 예측 결과 저장에 실패했습니다. 데이터베이스 연결 및 테이블 구조를 확인해주세요.")
    raise Exception("예측 결과 저장 실패 - predicted_stocks 테이블에 데이터가 없습니다!")

plt.figure(figsize=(12, 6))
plt.plot(history.history['loss'], label='Train Loss')
plt.title('Training Loss')
plt.xlabel('Epoch')
plt.ylabel('Loss')
plt.legend()
plt.show()

for col in target_columns:
    plt.figure(figsize=(12, 6))
    plt.plot(pd.to_datetime(result_data['날짜']), result_data[f'{col}_Actual'], label='Actual (Today)', alpha=0.7)
    plt.plot(pd.to_datetime(result_data['날짜']), result_data[f'{col}_Predicted'], label=f'Predicted ({forecast_horizon} days later)', alpha=0.7)
    plt.title(f'{col} - Actual(Today) vs Predicted({forecast_horizon} days later)')
    plt.xlabel('Date (Today)')
    plt.ylabel('Price')
    plt.legend()
    plt.xticks(rotation=45)
    plt.grid()
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    plt.gcf().autofmt_xdate()
    plt.close()

print(f"모든 예측 결과가 DB에 저장되었습니다.")

#################################### 결과 추론 ####################################
#################################### 결과 추론 ####################################
#################################### 결과 추론 ####################################

####################################
# [2단계] 예측 결과 분석 부분
# predicted_stocks 테이블에서 데이터를 읽어와서 분석합니다.
# [주의] 이 부분을 실행하기 전에 반드시 [1단계]가 먼저 실행되어야 합니다!
####################################

######################
# (0) Get Predictions From DB Function
######################

# Supabase에서 예측 데이터 가져오기 (청크 단위)
def get_predictions_from_db(chunk_size=1000):
    try:
        # 전체 레코드 수 확인
        count_response = supabase.table("predicted_stocks").select("id", count="exact").execute()
        total_count = count_response.count
        print(f"predicted_stocks 테이블의 총 레코드 수: {total_count}")

        # 데이터가 없으면 빈 DataFrame 반환
        if total_count == 0:
            print("경고: predicted_stocks 테이블이 비어있습니다.")
            return pd.DataFrame()

        # 데이터를 저장할 빈 리스트
        all_data = []

        # 청크 단위로 데이터 가져오기
        for offset in range(0, total_count, chunk_size):
            response = (
                supabase.table("predicted_stocks")
                .select("*")
                .order("날짜", desc=False)
                .limit(chunk_size)
                .offset(offset)
                .execute()
            )
            chunk_data = response.data
            print(f"오프셋 {offset}에서 {len(chunk_data)}개 데이터를 가져왔습니다.")
            all_data.extend(chunk_data)

        # 모든 데이터를 DataFrame으로 변환
        df = pd.DataFrame(all_data)
        print(f"총 {len(df)}개 데이터를 성공적으로 가져왔습니다!")
        
        # 디버깅: 실제 컬럼명 출력
        print(f"DataFrame 컬럼 수: {len(df.columns)}")
        print(f"컬럼명 샘플 (처음 10개): {list(df.columns[:10])}")
        
        # Predicted/Actual 컬럼이 있는지 확인
        predicted_cols = [col for col in df.columns if '_Predicted' in str(col)]
        actual_cols = [col for col in df.columns if '_Actual' in str(col)]
        print(f"Predicted 컬럼 수: {len(predicted_cols)}, 샘플: {predicted_cols[:5]}")
        print(f"Actual 컬럼 수: {len(actual_cols)}, 샘플: {actual_cols[:5]}")

        # 빈 DataFrame인 경우 체크
        if len(df) == 0:
            print("경고: 가져온 데이터가 없습니다.")
            return pd.DataFrame()

        # 날짜 열이 있는지 확인 후 datetime으로 변환
        if '날짜' in df.columns:
            df['날짜'] = pd.to_datetime(df['날짜'])
        else:
            print("경고: '날짜' 컬럼이 데이터에 없습니다.")
            return pd.DataFrame()

        return df
    except Exception as e:
        print(f"데이터 가져오기 오류: {e}")
        import traceback
        traceback.print_exc()
        return None

# 결과를 Supabase에 저장
def save_analysis_to_db(result_df):
    try:
        # 입력 데이터 검증
        if result_df is None or len(result_df) == 0:
            print("경고: 저장할 분석 결과 데이터가 없습니다.")
            return False
        
        # NaN 값을 None으로 변환 (JSON 직렬화를 위해 필수)
        # Supabase는 NaN을 지원하지 않으므로 None(null)로 변환해야 함
        result_df_clean = result_df.copy()
        result_df_clean = result_df_clean.replace([np.nan, np.inf, -np.inf], None)
        
        # stock_analysis_results 테이블에 저장
        records = result_df_clean.to_dict('records')
        
        # NaN이 남아있는지 확인 (디버깅용)
        nan_count = result_df.isna().sum().sum()
        if nan_count > 0:
            print(f"경고: {nan_count}개의 NaN 값이 None으로 변환되었습니다.")
        
        print(f"저장할 분석 결과 레코드 수: {len(records)}")

        # 테이블에 먼저 데이터 삭제 후 새로 삽입
        supabase.table("stock_analysis_results").delete().neq("id", 0).execute()
        print("기존 분석 결과 데이터 삭제 완료")

        # 일괄 삽입 (큰 데이터라면 청크로 나누어 삽입)
        chunk_size = 100
        total_inserted = 0
        for i in range(0, len(records), chunk_size):
            chunk = records[i:i+chunk_size]
            
            # 각 청크의 NaN 값을 None으로 변환 (이중 안전장치)
            for record in chunk:
                for key, value in record.items():
                    if isinstance(value, (float, np.floating)) and (np.isnan(value) or np.isinf(value)):
                        record[key] = None
            
            try:
                response = supabase.table("stock_analysis_results").insert(chunk).execute()
                total_inserted += len(chunk)
                print(f"청크 {i//chunk_size + 1}: {len(chunk)}개 레코드 삽입 완료")
            except Exception as chunk_error:
                print(f"청크 {i//chunk_size + 1} 삽입 실패: {chunk_error}")
                print(f"문제가 있는 청크의 첫 번째 레코드 샘플: {chunk[0] if chunk else 'None'}")
                raise

        print(f"총 {total_inserted}개의 분석 결과가 데이터베이스에 저장되었습니다.")
        
        # 저장 확인
        count_response = supabase.table("stock_analysis_results").select("id", count="exact").execute()
        saved_count = count_response.count
        print(f"저장 확인: stock_analysis_results 테이블에 {saved_count}개 레코드가 있습니다.")
        
        return True
    except Exception as e:
        print(f"데이터베이스 저장 오류: {e}")
        import traceback
        traceback.print_exc()
        return False

######################
# (1) Evaluation Function
######################
def evaluate_predictions(data, target_columns, forecast_horizon):
    """
    This function compares actual vs. predicted values (for the next 7 days)
    and computes various metrics such as MAE, MSE, RMSE, MAPE, and Accuracy.

    - MAE (Mean Absolute Error): Average absolute error between actual and predicted
      (lower is better, same unit as original data)
    - MSE (Mean Squared Error): Average of squared errors
      (lower is better)
    - RMSE (Root Mean Squared Error): Square root of MSE
      (lower is better, often used with MAE)
    - MAPE (Mean Absolute Percentage Error): Error as a percentage of the actual values
      (lower is better)
    - Accuracy (%): Computed as 100 - MAPE, serving as a simple accuracy measure
    """
    # 데이터 유효성 검사
    if data is None:
        print("경고: 평가할 데이터가 None입니다.")
        return pd.DataFrame()
    if len(data) == 0:
        print("경고: 평가할 데이터가 비어있습니다.")
        return pd.DataFrame()
    if not hasattr(data, 'columns'):
        print("경고: 데이터가 DataFrame 형식이 아닙니다.")
        return pd.DataFrame()

    metrics = []

    # 디버깅: 실제 컬럼명과 예상 컬럼명 비교
    print(f"\n=== 컬럼명 비교 디버깅 ===")
    print(f"DataFrame 컬럼 수: {len(data.columns)}")
    print(f"target_columns 수: {len(target_columns)}")
    
    # 실제 컬럼명 확인
    all_predicted_cols = [col for col in data.columns if '_Predicted' in str(col)]
    all_actual_cols = [col for col in data.columns if '_Actual' in str(col)]
    print(f"실제 Predicted 컬럼: {all_predicted_cols[:5]}...")
    print(f"실제 Actual 컬럼: {all_actual_cols[:5]}...")
    
    for col in target_columns:
        # 실제 컬럼명 찾기 (대소문자 구분 없이)
        predicted_col = None
        actual_col = None
        
        # 정확한 컬럼명 찾기
        for col_name in data.columns:
            col_str = str(col_name)
            # 주식명이 포함되고 Predicted/Actual이 포함된 컬럼 찾기
            if col in col_str:
                if '_Predicted' in col_str or 'Predicted' in col_str:
                    predicted_col = col_name
                if '_Actual' in col_str or 'Actual' in col_str:
                    actual_col = col_name
        
        # Check if the columns exist
        if predicted_col is None or actual_col is None:
            print(f"Skipping {col}: Columns not found in data")
            print(f"  예상 컬럼명: {col}_Predicted, {col}_Actual")
            print(f"  실제 유사 컬럼: {[c for c in data.columns if col in str(c)]}")
            continue
        
        # 디버깅: 찾은 컬럼명 출력 (처음 몇 개만)
        if target_columns.index(col) < 3:
            print(f"  {col}: {predicted_col}, {actual_col}")

        # Retrieve predicted and actual values
        predicted = data[predicted_col]
        # Shift the actual values by forecast_horizon days
        # so that today's prediction aligns with actual values 14 days ahead
        actual = data[actual_col].shift(-forecast_horizon)

        # Use only valid (non-NaN) indices
        valid_idx = ~predicted.isna() & ~actual.isna()
        predicted = predicted[valid_idx]
        actual = actual[valid_idx]

        if len(predicted) == 0:
            print(f"Skipping {col}: No valid prediction/actual pairs.")
            continue

        # Calculate metrics
        mae = mean_absolute_error(actual, predicted)
        mse = mean_squared_error(actual, predicted)
        rmse = mse ** 0.5
        mape = (abs((actual - predicted) / actual).mean()) * 100
        accuracy = 100 - mape

        metrics.append({
            'Stock': col,
            'MAE': mae,
            'MSE': mse,
            'RMSE': rmse,
            'MAPE (%)': mape,
            'Accuracy (%)': accuracy
        })

    # 빈 DataFrame을 반환할 때도 'Stock' 컬럼을 포함하도록 수정
    if len(metrics) == 0:
        return pd.DataFrame(columns=['Stock', 'MAE', 'MSE', 'RMSE', 'MAPE (%)', 'Accuracy (%)'])
    
    return pd.DataFrame(metrics)

###############################
# (2) Future Rise Analysis
###############################
def analyze_rise_predictions(data, target_columns):
    """
    This function looks at the last row of the DataFrame (most recent date),
    compares actual vs. predicted values, and calculates rise/fall information
    and rise probability in percentage.
    """
    # 데이터 유효성 검사
    if data is None:
        print("경고: 분석할 데이터가 None입니다.")
        return pd.DataFrame({
            'Stock': target_columns,
            'Last Actual Price': [np.nan] * len(target_columns),
            'Predicted Future Price': [np.nan] * len(target_columns),
            'Predicted Rise': [np.nan] * len(target_columns),
            'Rise Probability (%)': [np.nan] * len(target_columns)
        })
    
    # DataFrame이 비어있는지 확인 (여러 방법으로 체크)
    if not isinstance(data, pd.DataFrame):
        print("경고: 데이터가 DataFrame 형식이 아닙니다.")
        return pd.DataFrame({
            'Stock': target_columns,
            'Last Actual Price': [np.nan] * len(target_columns),
            'Predicted Future Price': [np.nan] * len(target_columns),
            'Predicted Rise': [np.nan] * len(target_columns),
            'Rise Probability (%)': [np.nan] * len(target_columns)
        })
    
    if len(data) == 0 or data.empty:
        print("경고: 분석할 데이터가 비어있습니다.")
        return pd.DataFrame({
            'Stock': target_columns,
            'Last Actual Price': [np.nan] * len(target_columns),
            'Predicted Future Price': [np.nan] * len(target_columns),
            'Predicted Rise': [np.nan] * len(target_columns),
            'Rise Probability (%)': [np.nan] * len(target_columns)
        })

    # 마지막 행 접근 시도
    try:
        if len(data) > 0:
            last_row = data.iloc[-1]
        else:
            print("경고: 데이터에 행이 없습니다.")
            return pd.DataFrame({
                'Stock': target_columns,
                'Last Actual Price': [np.nan] * len(target_columns),
                'Predicted Future Price': [np.nan] * len(target_columns),
                'Predicted Rise': [np.nan] * len(target_columns),
                'Rise Probability (%)': [np.nan] * len(target_columns)
            })
    except (IndexError, KeyError) as e:
        print(f"경고: 데이터 인덱스 접근 오류: {e}")
        return pd.DataFrame({
            'Stock': target_columns,
            'Last Actual Price': [np.nan] * len(target_columns),
            'Predicted Future Price': [np.nan] * len(target_columns),
            'Predicted Rise': [np.nan] * len(target_columns),
            'Rise Probability (%)': [np.nan] * len(target_columns)
        })

    results = []

    for col in target_columns:
        # 실제 컬럼명 찾기 (동적으로)
        predicted_col = None
        actual_col = None
        
        # 정확한 컬럼명 찾기
        for col_name in data.columns:
            col_str = str(col_name)
            # 주식명이 포함되고 Predicted/Actual이 포함된 컬럼 찾기
            if col in col_str:
                if '_Predicted' in col_str or 'Predicted' in col_str:
                    predicted_col = col_name
                if '_Actual' in col_str or 'Actual' in col_str:
                    actual_col = col_name
        
        # 컬럼을 찾지 못한 경우
        if predicted_col is None or actual_col is None:
            results.append({
                'Stock': col,
                'Last Actual Price': np.nan,
                'Predicted Future Price': np.nan,
                'Predicted Rise': np.nan,
                'Rise Probability (%)': np.nan
            })
            continue

        last_actual_price = last_row.get(actual_col, np.nan)
        predicted_future_price = last_row.get(predicted_col, np.nan)

        # Determine rise/fall and rise percentage
        if pd.notna(last_actual_price) and pd.notna(predicted_future_price):
            predicted_rise = predicted_future_price > last_actual_price
            rise_probability = ((predicted_future_price - last_actual_price) / last_actual_price) * 100
        else:
            predicted_rise = np.nan
            rise_probability = np.nan

        results.append({
            'Stock': col,
            'Last Actual Price': last_actual_price,
            'Predicted Future Price': predicted_future_price,
            'Predicted Rise': predicted_rise,
            'Rise Probability (%)': rise_probability
        })

    return pd.DataFrame(results)

#######################################
# (3) Buy/Sell Recommendation and Analysis
#######################################
def generate_recommendation(row):
    """
    Example logic:
    - (Predicted Rise == True) and (Rise Probability > 0) => BUY
    - (Rise Probability > 2) => STRONG BUY
    - Otherwise => SELL
    """
    rise_prob = row.get('Rise Probability (%)', 0)
    predicted_rise = row.get('Predicted Rise', False)

    if pd.isna(rise_prob) or pd.isna(predicted_rise):
        return "No Data"

    if predicted_rise and rise_prob > 0:
        if rise_prob > 2:
            return "STRONG BUY"
        else:
            return "BUY"
    else:
        return "SELL"

def generate_analysis(row):
    """
    Provides a one-line comment for each entry.
    Stock: stock name
    Rise Probability (%): approximate rise probability
    """
    stock_name = row['Stock']
    rise_prob = row.get('Rise Probability (%)', 0)
    predicted_rise = row.get('Predicted Rise', False)

    if pd.isna(rise_prob) or pd.isna(predicted_rise):
        return f"{stock_name}: Not enough data"

    if predicted_rise:
        return f"{stock_name} is expected to rise by about {rise_prob:.2f}%. Consider buying or holding."
    else:
        return f"{stock_name} is expected to fall by about {-rise_prob:.2f}%. A cautious approach is recommended."

#######################
# (4) Main Code - [2단계] 예측 결과 분석
#######################
print("=" * 60)
print("[2단계] 예측 결과 분석 시작")
print("=" * 60)
# 1) Load Data from Supabase (predicted_stocks 테이블에서 읽기)
print("predicted_stocks 테이블에서 데이터 로드 중...")
data = get_predictions_from_db(chunk_size=1000)
if data is None:
    print("데이터를 가져오는데 실패했습니다. (None 반환)")
    exit(1)
if len(data) == 0:
    print("=" * 60)
    print("경고: predicted_stocks 테이블이 비어있습니다!")
    print("=" * 60)
    print("\n모델 학습 및 예측을 실행하여 predicted_stocks 테이블에 데이터를 생성해야 합니다.")
    print("코드의 178-361줄 부분(모델 학습 및 예측)을 먼저 실행해주세요.")
    print("\n또는 전체 스크립트를 처음부터 실행하면 자동으로:")
    print("  1) 모델 학습 및 예측 (178-361줄)")
    print("  2) predicted_stocks 테이블에 저장 (335줄)")
    print("  3) 결과 분석 (712줄 이후)")
    print("순서로 실행됩니다.")
    print("=" * 60)
    exit(1)

# 2) Target columns
target_columns = [
    '애플', '마이크로소프트', '아마존', '구글 A', '구글 C', '메타',
    '테슬라', '엔비디아', '인텔', '마이크론', '브로드컴',
    '텍사스 인스트루먼트', 'AMD', '어플라이드 머티리얼즈',
    '셀레스티카', '버티브 홀딩스', '비스트라 에너지', '블룸에너지', '오클로', '팔란티어',
    '세일즈포스', '오라클', '앱플로빈', '팔로알토 네트웍스', '크라우드 스트라이크',
    '스노우플레이크', 'TSMC', '크리도 테크놀로지 그룹 홀딩', '로빈후드', '일라이릴리',
    '월마트', '존슨앤존슨', 'S&P 500 ETF', 'QQQ ETF'
]

forecast_horizon = 14  # predicting 14 days ahead

# 3) Evaluate predictions
evaluation_results = evaluate_predictions(data, target_columns, forecast_horizon)
print("============ Evaluation Results ============")
print(evaluation_results)

# 4) Analyze future rise
rise_results = analyze_rise_predictions(data, target_columns)
print("============ Rise Predictions ============")
print(rise_results)

# 5) Merge 전 검증
if evaluation_results.empty:
    print("경고: evaluation_results가 비어있습니다. 'Stock' 컬럼이 있는 빈 DataFrame으로 초기화합니다.")
    evaluation_results = pd.DataFrame(columns=['Stock', 'MAE', 'MSE', 'RMSE', 'MAPE (%)', 'Accuracy (%)'])

if rise_results.empty:
    print("경고: rise_results가 비어있습니다. 'Stock' 컬럼이 있는 빈 DataFrame으로 초기화합니다.")
    rise_results = pd.DataFrame(columns=['Stock', 'Last Actual Price', 'Predicted Future Price', 'Predicted Rise', 'Rise Probability (%)'])

# 'Stock' 컬럼이 있는지 확인
if 'Stock' not in evaluation_results.columns:
    print("경고: evaluation_results에 'Stock' 컬럼이 없습니다. 추가합니다.")
    if len(evaluation_results) > 0:
        evaluation_results.insert(0, 'Stock', target_columns[:len(evaluation_results)])
    else:
        evaluation_results['Stock'] = []

if 'Stock' not in rise_results.columns:
    print("경고: rise_results에 'Stock' 컬럼이 없습니다. 추가합니다.")
    if len(rise_results) > 0:
        rise_results.insert(0, 'Stock', target_columns[:len(rise_results)])
    else:
        rise_results['Stock'] = []

# 6) Merge DataFrames (evaluation metrics + rise analysis)
final_results = pd.merge(evaluation_results, rise_results, on='Stock', how='outer')

# 7) Sort by rise probability (descending order)
final_results = final_results.sort_values(by='Rise Probability (%)', ascending=False)

# 8) Generate buy/sell recommendations and analysis
final_results['Recommendation'] = final_results.apply(generate_recommendation, axis=1)
final_results['Analysis'] = final_results.apply(generate_analysis, axis=1)

# Reorder columns
column_order = [
    'Stock',
    'MAE', 'MSE', 'RMSE', 'MAPE (%)', 'Accuracy (%)',
    'Last Actual Price', 'Predicted Future Price', 'Predicted Rise', 'Rise Probability (%)',
    'Recommendation', 'Analysis'
]
final_results = final_results[column_order]

# 9) Save final results to Supabase
save_analysis_to_db(final_results)
print("\n분석 결과가 'stock_analysis_results' 테이블에 저장되었습니다.")

# 10) Print final report
print("=============== Final Report ===============")
print(final_results.to_string(index=False))
