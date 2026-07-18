import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Bankers } from './bankers';

describe('Bankers', () => {
  let component: Bankers;
  let fixture: ComponentFixture<Bankers>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Bankers],
    }).compileComponents();

    fixture = TestBed.createComponent(Bankers);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
