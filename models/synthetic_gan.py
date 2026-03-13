import torch
import torch.nn as nn
import torch.optim as optim
import pandas as pd
import numpy as np
import os

class Generator(nn.Module):
    def __init__(self, input_dim=10, hidden_dim=64, output_dim=5):
        super(Generator, self).__init__()
        # Input: random noise (batch_size, seq_length, input_dim)
        self.lstm = nn.LSTM(input_dim, hidden_dim, batch_first=True)
        # Output: synthetic OHLCV (batch_size, seq_length, output_dim)
        self.linear = nn.Linear(hidden_dim, output_dim)

    def forward(self, x):
        lstm_out, _ = self.lstm(x)
        out = self.linear(lstm_out)
        return out

class Discriminator(nn.Module):
    def __init__(self, input_dim=5, hidden_dim=64):
        super(Discriminator, self).__init__()
        # Input: sequence of OHLCV (batch_size, seq_length, input_dim)
        self.lstm = nn.LSTM(input_dim, hidden_dim, batch_first=True)
        # Output: probability Real (1) vs Fake (0)
        self.linear = nn.Linear(hidden_dim, 1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        lstm_out, _ = self.lstm(x)
        # We only care about the final prediction for the entire sequence context
        last_out = lstm_out[:, -1, :]
        out = self.linear(last_out)
        return self.sigmoid(out)

def train_gan(real_data_csv, epochs=100, batch_size=32, seq_length=60, input_dim=10):
    """
    Trains the GAN on historical market data to generate realistic Black Swan events.
    """
    print(f"Loading real data from {real_data_csv}...")
    df = pd.read_csv(real_data_csv)
    
    # Extract OHLCV or fallback to the first 5 numeric columns
    cols = [c for c in ['open', 'high', 'low', 'close', 'volume'] if c in df.columns.str.lower()]
    if len(cols) < 5:
        cols = df.select_dtypes(include=[np.number]).columns[:5].tolist()
        
    data = df[cols].values
    
    # Normalize data between 0 and 1 for stable GAN training
    data_min, data_max = np.min(data, axis=0), np.max(data, axis=0)
    data_normalized = (data - data_min) / (data_max - data_min + 1e-8)

    # Slice into sequences
    sequences = []
    for i in range(len(data_normalized) - seq_length):
        sequences.append(data_normalized[i : i + seq_length])
        
    dataset = torch.tensor(np.array(sequences), dtype=torch.float32)
    dataloader = torch.utils.data.DataLoader(dataset, batch_size=batch_size, shuffle=True)

    generator = Generator(input_dim=input_dim, output_dim=5)
    discriminator = Discriminator(input_dim=5)

    criterion = nn.BCELoss()
    opt_g = optim.Adam(generator.parameters(), lr=0.0002)
    opt_d = optim.Adam(discriminator.parameters(), lr=0.0002)

    print("Starting GAN training loop...")
    for epoch in range(epochs):
        for real_seq in dataloader:
            b_size = real_seq.size(0)
            
            # --- 1. Train Discriminator ---
            opt_d.zero_grad()
            real_labels = torch.ones(b_size, 1)
            fake_labels = torch.zeros(b_size, 1)
            
            # Predict on real data
            out_real = discriminator(real_seq)
            loss_real = criterion(out_real, real_labels)
            
            # Generate fake data and predict
            noise = torch.randn(b_size, seq_length, input_dim)
            fake_seq = generator(noise)
            out_fake = discriminator(fake_seq.detach())
            loss_fake = criterion(out_fake, fake_labels)
            
            loss_d = loss_real + loss_fake
            loss_d.backward()
            opt_d.step()
            
            # --- 2. Train Generator ---
            opt_g.zero_grad()
            out_fake_for_g = discriminator(fake_seq)
            # Generator wants Discriminator to guess 1 (Real)
            loss_g = criterion(out_fake_for_g, real_labels)
            loss_g.backward()
            opt_g.step()

        if (epoch + 1) % 10 == 0:
            print(f"Epoch [{epoch+1}/{epochs}] | D Loss: {loss_d.item():.4f} | G Loss: {loss_g.item():.4f}")

    os.makedirs('models', exist_ok=True)
    torch.save(generator.state_dict(), 'models/midas_generator.pth')
    print("Training complete. Generator saved to models/midas_generator.pth")

def generate_synthetic_data(num_samples, input_dim=10):
    """
    Hallucinates a synthetic market history dataframe.
    """
    generator = Generator(input_dim=input_dim, output_dim=5)
    model_path = 'models/midas_generator.pth'
    
    if os.path.exists(model_path):
        generator.load_state_dict(torch.load(model_path))
        generator.eval()
        print("Loaded trained Generator weights.")
    else:
        print(f"Warning: {model_path} not found. Generating with randomized initial weights.")

    with torch.no_grad():
        # Generate a single continuous sequence of length 'num_samples'
        noise = torch.randn(1, num_samples, input_dim)
        synthetic_seq = generator(noise)
    
    synthetic_data = synthetic_seq.squeeze(0).numpy()
    
    df = pd.DataFrame(synthetic_data, columns=['open', 'high', 'low', 'close', 'volume'])
    print(f"Generated {num_samples} synthetic candles.")
    return df