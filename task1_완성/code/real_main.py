import argparse
import torch
from transformers import BertTokenizer, BertForSequenceClassification
import utility
from transformers import MBartForConditionalGeneration, MBart50TokenizerFast
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db
from datetime import datetime


#Firebase database 인증 및 앱 초기화
cred = credentials.Certificate('./mykey.json')
firebase_admin.initialize_app(cred,{'databaseURL':'https://ybigta-project-mbti-default-rtdb.firebaseio.com/'})


if __name__ == '__main__':
    # 1. 사용자 답변 번역
    dir=db.reference().child('task1').child('UserAnswer').get() #기본 위치 지정
    latest_timestamp = None
    value = None

    for key in dir:
        date_obj = datetime.strptime(key, "%Y%m%d%H%M%S")

        if latest_timestamp is None or date_obj.timestamp() > latest_timestamp:
            latest_timestamp = date_obj.timestamp()
            latest_key = key

    answers = ' '.join(s for s in dir[latest_key]) 

    model_translate = MBartForConditionalGeneration.from_pretrained('mbart_model')
    tokenizer_translate = MBart50TokenizerFast.from_pretrained('mbart_tokenizer')
    tokenizer_translate.src_lang = 'ko_KR'
    encoded_hi = tokenizer_translate(answers, return_tensors='pt')
    generated_tokens = model_translate.generate(
        **encoded_hi,
        forced_bos_token_id=tokenizer_translate.lang_code_to_id['en_XX']
    )
    translated_input = tokenizer_translate.batch_decode(generated_tokens, skip_special_tokens=True)[0] # save translated text.

    cleaned_text = utility.preprocess_text(translated_input)

    # 2. 모델 예측
    tokenizer = BertTokenizer.from_pretrained('bert_tokenizer')
    model = BertForSequenceClassification.from_pretrained('bert_model')
    model.load_state_dict(torch.load('../model/best_model.pth', map_location=torch.device('cpu')))
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    model.eval()

    encoded_input = tokenizer.encode_plus(
        cleaned_text,
        add_special_tokens=True,
        max_length=64,
        padding='max_length',
        return_attention_mask=True,
        truncation=True,
        return_tensors='pt'
    )
    input_ids = encoded_input['input_ids'].to(device)
    attention_mask = encoded_input['attention_mask'].to(device)

    with torch.no_grad():
        outputs = model(input_ids, attention_mask=attention_mask)
        logits = outputs.logits

    predicted_label_idx = torch.argmax(logits, dim=1).cpu().numpy()[0]
    predicted_label = utility.idx_to_mbti(predicted_label_idx)
    pred_type_demo = utility.print_demo(predicted_label)

    # 사용자의 mbti를 데이터베이스에 저장
    user_ref = db.reference().child("task1").child("UserAnswer").child(latest_key)
    new_content = [predicted_label, pred_type_demo]
    user_ref.update({"mbti": new_content})
    print(f'''당신의 MBTI는 {predicted_label}이고, 이 MBTI의 {pred_type_demo}''')
